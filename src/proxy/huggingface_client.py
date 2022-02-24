from common.cache import Cache
from common.hierarchical_logger import htrack_block
from common.request import Request, RequestResult, Sequence, Token
from .client import Client, wrap_request_time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Any, Dict, List


class HuggingFaceServer:
    def __init__(self, model_name: str):
        self.device: str = "cuda:0" if torch.cuda.is_available() else "cpu"

        with htrack_block("Loading model"):
            self.model = AutoModelForCausalLM.from_pretrained(model_name).to(self.device)
        with htrack_block("Loading tokenizer"):
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def serve_request(self, raw_request: Dict[str, Any]):
        encoded_input = self.tokenizer(raw_request["prompt"], return_tensors="pt").to(self.device)

        raw_request["do_sample"] = True
        raw_request["return_dict_in_generate"] = True
        raw_request["output_scores"] = True

        output = self.model.generate(**encoded_input, **raw_request)
        sequences = output.sequences
        scores = output.scores

        # Compute logprobs for each completed sequence.
        all_logprobs_of_chosen_tokens = []
        for completion_id in range(raw_request["num_return_sequences"]):
            logprobs_of_chosen_tokens = []
            for i in range(len(sequences[completion_id]) - len(encoded_input.input_ids[0])):
                logprobs = torch.nn.functional.log_softmax(scores[i][completion_id], dim=0)

                # Get log probability of chosen token.
                j = i + len(encoded_input.input_ids[0])
                logprobs_of_chosen_tokens.append(logprobs[sequences[completion_id][j]].item())
            all_logprobs_of_chosen_tokens.append(logprobs_of_chosen_tokens)

        # Remove prompt from the start of each sequence if echo_prompt is False.
        if not raw_request["echo_prompt"]:
            sequences = [sequence[len(encoded_input.input_ids[0]) :] for sequence in sequences]
        # TODO: Get rid of the extra tokenization?
        all_tokens = [self.tokenizer.convert_ids_to_tokens(sequence) for sequence in sequences]
        all_decoded_text = self.tokenizer.batch_decode(sequences)

        completions = []
        for (decoded_text, tokens, logprobs_of_chosen_tokens) in zip(
            all_decoded_text, all_tokens, all_logprobs_of_chosen_tokens
        ):
            # TODO: Populate top_logprobs as well?
            completions.append({"text": decoded_text, "tokens": tokens, "logprobs": logprobs_of_chosen_tokens})

        return {"completions": completions, "input_length": len(encoded_input.input_ids[0])}


class HuggingFaceClient(Client):
    def __init__(self, cache_path: str):
        self.cache = Cache(cache_path)
        self.model_server_instances: Dict[str, HuggingFaceServer] = {}

    def get_model_server_instance(self, model_engine):
        if model_engine not in self.model_server_instances:
            if model_engine == "gptj_6b":
                self.model_server_instances[model_engine] = HuggingFaceServer("EleutherAI/gpt-j-6B")
            elif model_engine == "gpt2":
                self.model_server_instances[model_engine] = HuggingFaceServer("gpt2")
            else:
                raise Exception("Unknown model!")
        return self.model_server_instances[model_engine]

    def make_request(self, request: Request) -> RequestResult:
        raw_request = {
            "engine": request.model_engine,
            "prompt": request.prompt,
            "temperature": request.temperature,
            "num_return_sequences": request.num_completions,
            "max_length": request.max_tokens,
            "top_k": request.top_k_per_token,
            "top_p": request.top_p,
            "echo_prompt": request.echo_prompt,
        }
        model_server_instance = self.get_model_server_instance(request.model_engine)

        try:

            def do_it():
                return model_server_instance.serve_request(raw_request)

            cache_key = Client.make_cache_key(raw_request, request)
            response, cached = self.cache.get(cache_key, wrap_request_time(do_it))
        except Exception as e:  # Do something if error is encountered.
            error: str = f"HuggingFace error: {e}"
            return RequestResult(success=False, cached=False, error=error, completions=[])

        completions = []
        for raw_completion in response["completions"]:
            sequence_logprob = 0
            tokens: List[Token] = []

            if request.echo_prompt:
                generated_tokens = raw_completion["tokens"][response["input_length"] :]
                for token_text in raw_completion["tokens"][: response["input_length"]]:
                    tokens.append(Token(text=token_text, logprob=0.0, top_logprobs={}))
            else:
                generated_tokens = raw_completion["tokens"]
            for token_text, logprob in zip(generated_tokens, raw_completion["logprobs"]):
                tokens.append(Token(text=token_text, logprob=logprob, top_logprobs={}))
                sequence_logprob += logprob
            completion = Sequence(text=raw_completion["text"], logprob=sequence_logprob, tokens=tokens)
            completions.append(completion)
        return RequestResult(
            success=True, cached=cached, request_time=response["request_time"], completions=completions
        )
