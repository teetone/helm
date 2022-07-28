from .huggingface_tokenizer import HuggingFaceTokenizers


class TestHuggingFaceTokenizers:
    # The following prompt has 51 tokens according to the GPT-2 tokenizer
    TEST_PROMPT: str = (
        "The Center for Research on Foundation Models (CRFM) is "
        "an interdisciplinary initiative born out of the Stanford "
        "Institute for Human-Centered Artificial Intelligence (HAI) "
        "that aims to make fundamental advances in the study, development, "
        "and deployment of foundation models."
    )

    @staticmethod
    def verify_get_tokenizer(tokenizer_name: str, expected_num_tokens: int):
        tokenizer = HuggingFaceTokenizers.get_tokenizer(tokenizer_name)
        assert tokenizer_name in HuggingFaceTokenizers.tokenizers, "Tokenizer should be cached"
        assert len(tokenizer.tokenize(TestHuggingFaceTokenizers.TEST_PROMPT)) == expected_num_tokens

    def test_get_tokenizer_gpt2(self):
        TestHuggingFaceTokenizers.verify_get_tokenizer("huggingface/gpt2", 51)

    def test_get_tokenizer_gptj(self):
        TestHuggingFaceTokenizers.verify_get_tokenizer("huggingface/gpt-j-6b", 51)

    def test_get_tokenizer_gptneox(self):
        TestHuggingFaceTokenizers.verify_get_tokenizer("huggingface/gpt-neox-20b", 52)

    def test_get_tokenizer_t0pp(self):
        TestHuggingFaceTokenizers.verify_get_tokenizer("bigscience/T0pp", 57)

    def test_get_tokenizer_t511b(self):
        TestHuggingFaceTokenizers.verify_get_tokenizer("google/t5-11b", 57)

    def test_get_tokenizer_ul2(self):
        TestHuggingFaceTokenizers.verify_get_tokenizer("google/ul2", 57)
