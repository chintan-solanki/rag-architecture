import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from common.helpers.llmfactory import create_llm


class LLMFactoryTests(unittest.TestCase):
    def test_creates_configured_provider_with_its_api_key(self) -> None:
        for provider, module_name, class_name, key_name in (
            ("openai", "llama_index.llms.openai", "OpenAI", "OPENAI_API_KEY"),
            (
                "gemini",
                "llama_index.llms.google_genai",
                "GoogleGenAI",
                "GOOGLE_API_KEY",
            ),
            (
                "anthropic",
                "llama_index.llms.anthropic",
                "Anthropic",
                "ANTHROPIC_API_KEY",
            ),
        ):
            with self.subTest(provider=provider):
                constructor_args: dict[str, str] = {}

                class FakeLLM:
                    def __init__(self, **kwargs: str) -> None:
                        constructor_args.update(kwargs)

                def importer(name: str) -> SimpleNamespace:
                    self.assertEqual(name, module_name)
                    return SimpleNamespace(**{class_name: FakeLLM})

                with patch.dict(os.environ, {key_name: "test-api-key"}):
                    llm = create_llm(
                        {
                            "provider": provider,
                            "model": "test-model",
                            "api_key_env": key_name,
                        },
                        importer=importer,
                    )

                self.assertIsInstance(llm, FakeLLM)
                self.assertEqual(
                    constructor_args,
                    {"model": "test-model", "api_key": "test-api-key"},
                )

    def test_defaults_provider_and_key_name_to_openai(self) -> None:
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-api-key"}),
            patch(
                "common.helpers.llmfactory.importlib.import_module",
                return_value=SimpleNamespace(
                    OpenAI=lambda **kwargs: SimpleNamespace(**kwargs)
                ),
            ) as importer,
        ):
            llm = create_llm({"model": "gpt-4o-mini"})

        importer.assert_called_once_with("llama_index.llms.openai")
        self.assertEqual(
            vars(llm),
            {"model": "gpt-4o-mini", "api_key": "test-api-key"},
        )

    def test_missing_selected_api_key_fails_explicitly(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_API_KEY"):
                create_llm(
                    {
                        "provider": "gemini",
                        "model": "test-model",
                        "api_key_env": "GOOGLE_API_KEY",
                    }
                )

    def test_unsupported_provider_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported LLM provider"):
            create_llm({"provider": "other", "model": "test-model"})


if __name__ == "__main__":
    unittest.main()
