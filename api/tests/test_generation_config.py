import unittest
from types import SimpleNamespace

from api.src.models.query import GenerationConfig
from api.src.services.generation import GenerationService


class FakeLLM:
    def __init__(self) -> None:
        self.complete_call: tuple[str, dict[str, float | int]] | None = None
        self.stream_call: tuple[str, dict[str, float | int]] | None = None

    def complete(self, prompt: str, **kwargs: float | int) -> SimpleNamespace:
        self.complete_call = (prompt, kwargs)
        return SimpleNamespace(text="Generated answer.")

    def stream_complete(self, prompt: str, **kwargs: float | int):
        self.stream_call = (prompt, kwargs)
        yield SimpleNamespace(delta="Generated answer.")


class GenerationConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = GenerationService({"llm": {"model": "gpt-4o-mini"}})
        self.llm = FakeLLM()
        self.service._llm = self.llm
        self.generation_config = GenerationConfig(
            temperature=0.4,
            max_output_tokens=384,
            top_p=0.85,
        )
        self.expected_kwargs = {
            "temperature": 0.4,
            "top_p": 0.85,
            "max_tokens": 384,
        }

    def test_generate_applies_generation_config_to_llm_call(self) -> None:
        answer = self.service.generate("question", "context", self.generation_config)

        self.assertEqual(answer, "Generated answer.")
        self.assertEqual(
            self.llm.complete_call,
            (self.service.prompt("question", "context"), self.expected_kwargs),
        )

    def test_stream_applies_generation_config_to_llm_call(self) -> None:
        chunks = list(self.service.stream("question", "context", self.generation_config))

        self.assertEqual(chunks, ["Generated answer."])
        self.assertEqual(
            self.llm.stream_call,
            (self.service.prompt("question", "context"), self.expected_kwargs),
        )

    def test_none_generation_values_are_not_forwarded(self) -> None:
        config = GenerationConfig(
            temperature=None,
            max_output_tokens=None,
            top_p=None,
        )

        self.service.generate("question", "context", config)

        self.assertEqual(
            self.llm.complete_call,
            (self.service.prompt("question", "context"), {}),
        )


if __name__ == "__main__":
    unittest.main()
