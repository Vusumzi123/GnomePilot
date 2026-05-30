"""LLM instance factory — dispatches by provider key.

Single public function ``create_llm()`` that takes a flat config dict
and returns the appropriate LangChain chat model instance.

Adding a new provider means adding one case to ``_PROVIDERS`` and one
kwarg allowlist to ``_PROVIDER_KWARGS``.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

_logger = logging.getLogger(__name__)

# Provider dispatch table: provider name → (class, default_base_url)
# Classes are lazy-imported to avoid hard dependencies at module level.
_PROVIDERS: dict[str, tuple[str, str | None]] = {
    "ollama": ("langchain_ollama.ChatOllama", None),
    "openai": ("langchain_openai.ChatOpenAI", "https://api.openai.com/v1"),
    "deepseek": ("langchain_openai.ChatOpenAI", "https://api.deepseek.com"),
    "qwen": ("langchain_openai.ChatOpenAI",
              "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "openrouter": ("langchain_openai.ChatOpenAI", "https://openrouter.ai/api/v1"),
}

# Allowed kwargs per provider. Unknown kwargs are silently dropped (debug log).
_OPENAI_COMPAT_KWARGS = {
    "model", "temperature", "stop", "callbacks",
    "base_url", "api_key", "max_tokens", "top_p",
}

_PROVIDER_KWARGS: dict[str, set[str]] = {
    "ollama": {
        "model", "temperature", "stop", "callbacks",
        "num_ctx", "keep_alive",
    },
    "openai": _OPENAI_COMPAT_KWARGS,
    "deepseek": _OPENAI_COMPAT_KWARGS,
    "qwen": _OPENAI_COMPAT_KWARGS,
    "openrouter": _OPENAI_COMPAT_KWARGS,
}


def _import_class(dotted_path: str) -> type:
    """Lazy-import a class by dotted path (e.g. 'langchain_ollama.ChatOllama')."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def create_llm(
    config: dict[str, Any],
    callbacks: list | None = None,
) -> BaseChatModel:
    """Build a LangChain chat model instance from a provider config dict.

    Args:
        config: Flat dict with at least ``{"provider": "...", "model": "..."}``.
                All keys are filtered per-provider before passing to the
                constructor. Unknown kwargs are silently dropped.
        callbacks: Optional list of LangChain callback handlers.

    Returns:
        A BaseChatModel subclass instance (ChatOllama, ChatOpenAI, etc.)

    Raises:
        ValueError: If the provider is unknown.
    """
    provider = config.get("provider", "ollama")
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider!r}. "
            f"Supported: {', '.join(sorted(_PROVIDERS))}"
        )

    class_path, default_base_url = _PROVIDERS[provider]
    allowed = _PROVIDER_KWARGS[provider]

    # Filter kwargs to only those allowed for this provider
    filtered: dict[str, Any] = {}
    for key, value in config.items():
        if key == "provider":
            continue  # provider is not a constructor arg
        if key in allowed:
            filtered[key] = value
        elif key not in ("model", "temperature", "stop"):
            # model/temperature/stop are universal — drop silently without log
            pass
        else:
            _logger.debug(
                "Dropping kwarg %r=%r for provider %r", key, value, provider
            )

    # Attach callbacks if provided
    if callbacks:
        filtered["callbacks"] = callbacks

    # Apply default base_url for providers that support it (OpenAI compat)
    if "base_url" in allowed and "base_url" not in filtered and default_base_url:
        filtered["base_url"] = default_base_url

    cls = _import_class(class_path)
    return cls(**filtered)
