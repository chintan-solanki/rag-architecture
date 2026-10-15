import importlib
import os
from collections.abc import Callable
from typing import Any


_PROVIDERS: dict[str, tuple[str, str, str]] = {
    "openai": ("llama_index.llms.openai", "OpenAI", "OPENAI_API_KEY"),
    "gemini": (
        "llama_index.llms.google_genai",
        "GoogleGenAI",
        "GOOGLE_API_KEY",
    ),
    "anthropic": (
        "llama_index.llms.anthropic",
        "Anthropic",
        "ANTHROPIC_API_KEY",
    ),
}


def create_llm(
    config: dict[str, Any],
    *,
    importer: Callable[[str], Any] | None = None,
) -> Any:
    provider = str(config.get("provider", "openai")).strip().lower()
    provider_config = _PROVIDERS.get(provider)
    if provider_config is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise ValueError(
            f"Unsupported LLM provider {provider!r}. Supported providers: {supported}."
        )

    model = config.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("LLM configuration must include a non-empty 'model'.")

    module_name, class_name, default_key_env = provider_config
    api_key_env = config.get("api_key_env", default_key_env)
    if not isinstance(api_key_env, str) or not api_key_env.strip():
        raise ValueError("LLM configuration 'api_key_env' must be a non-empty string.")

    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(
            f"LLM provider {provider!r} requires the {api_key_env} environment variable."
        )

    try:
        load_module = importer or importlib.import_module
        llm_class = getattr(load_module(module_name), class_name)
    except ImportError as exc:
        raise RuntimeError(
            f"LLM provider {provider!r} requires its LlamaIndex adapter package."
        ) from exc

    return llm_class(model=model, api_key=api_key)
