"""Tests for src/model_factory.py — LLM instance factory."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.model_factory import create_llm


def _mock_import_class(fake_cls):
    """Patch _import_class to return a fake constructor that captures kwargs."""
    def _patcher():
        return patch(
            "src.model_factory._import_class",
            return_value=fake_cls,
        )
    return _patcher


def test_ollama_returns_chatollama():
    """Valid ollama config → instance of the correct class."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance

    with _mock_import_class(mock_cls)():
        result = create_llm({"provider": "ollama", "model": "llama3.1:8b"})

    assert result is mock_instance
    mock_cls.assert_called_once()
    # Check model was passed
    assert mock_cls.call_args[1].get("model") == "llama3.1:8b"
    print("  ollama → ChatOllama: OK")


def test_openai_returns_chatopenai():
    """Valid openai config → instance of the correct class."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance

    with _mock_import_class(mock_cls)():
        result = create_llm({
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test",
        })

    assert result is mock_instance
    mock_cls.assert_called_once()
    kwargs = mock_cls.call_args[1]
    assert kwargs.get("model") == "gpt-4o"
    assert kwargs.get("api_key") == "sk-test"
    assert kwargs.get("base_url") == "https://api.openai.com/v1"
    print("  openai → ChatOpenAI: OK")


def test_unknown_provider_raises():
    """Unknown provider → ValueError."""
    try:
        create_llm({"provider": "nonexistent", "model": "foo"})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)
    print("  unknown provider raises ValueError: OK")


def test_ollama_num_ctx_passed_through():
    """num_ctx in ollama config reaches the constructor."""
    mock_cls = MagicMock()
    mock_cls.return_value = MagicMock()

    with _mock_import_class(mock_cls)():
        create_llm({"provider": "ollama", "model": "test", "num_ctx": 4096})

    kwargs = mock_cls.call_args[1]
    assert kwargs.get("num_ctx") == 4096
    print("  ollama num_ctx passed through: OK")


def test_openai_num_ctx_silently_dropped():
    """num_ctx in openai config is dropped (not an OpenAI param)."""
    mock_cls = MagicMock()
    mock_cls.return_value = MagicMock()

    with _mock_import_class(mock_cls)():
        create_llm({
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test",
            "num_ctx": 4096,
        })

    kwargs = mock_cls.call_args[1]
    assert "num_ctx" not in kwargs
    print("  openai num_ctx silently dropped: OK")


def test_callbacks_attached():
    """Callbacks list reaches the constructor."""
    mock_cls = MagicMock()
    mock_cls.return_value = MagicMock()
    fake_cb = MagicMock()

    with _mock_import_class(mock_cls)():
        create_llm(
            {"provider": "ollama", "model": "test"},
            callbacks=[fake_cb],
        )

    kwargs = mock_cls.call_args[1]
    assert "callbacks" in kwargs
    assert kwargs["callbacks"] == [fake_cb]
    print("  callbacks attached: OK")


def test_ollama_unknown_kwarg_filtered():
    """Unknown kwarg silently dropped for ollama."""
    mock_cls = MagicMock()
    mock_cls.return_value = MagicMock()

    with _mock_import_class(mock_cls)():
        create_llm({
            "provider": "ollama",
            "model": "test",
            "api_key": "should-be-dropped",
        })

    kwargs = mock_cls.call_args[1]
    assert "api_key" not in kwargs
    print("  ollama unknown kwarg filtered: OK")


def test_openai_unknown_kwarg_filtered():
    """Unknown kwarg silently dropped for openai."""
    mock_cls = MagicMock()
    mock_cls.return_value = MagicMock()

    with _mock_import_class(mock_cls)():
        create_llm({
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-test",
            "keep_alive": 0,
        })

    kwargs = mock_cls.call_args[1]
    assert "keep_alive" not in kwargs
    print("  openai unknown kwarg filtered: OK")


# ── Phase 2: DeepSeek, Qwen, OpenRouter ──


def test_deepseek_returns_chatopenai():
    """DeepSeek config → ChatOpenAI with correct base_url."""
    mock_cls = MagicMock()
    mock_cls.return_value = MagicMock()

    with _mock_import_class(mock_cls)():
        create_llm({
            "provider": "deepseek",
            "model": "deepseek-chat",
            "api_key": "sk-test",
        })

    kwargs = mock_cls.call_args[1]
    assert kwargs.get("model") == "deepseek-chat"
    assert kwargs.get("base_url") == "https://api.deepseek.com"
    assert kwargs.get("api_key") == "sk-test"
    print("  deepseek → ChatOpenAI with deepseek base_url: OK")


def test_qwen_returns_chatopenai():
    """Qwen config → ChatOpenAI with dashscope base_url."""
    mock_cls = MagicMock()
    mock_cls.return_value = MagicMock()

    with _mock_import_class(mock_cls)():
        create_llm({
            "provider": "qwen",
            "model": "qwen-turbo",
            "api_key": "sk-test",
        })

    kwargs = mock_cls.call_args[1]
    assert kwargs.get("model") == "qwen-turbo"
    assert kwargs.get("base_url") == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    print("  qwen → ChatOpenAI with dashscope base_url: OK")


def test_openrouter_returns_chatopenai():
    """OpenRouter config → ChatOpenAI with openrouter.ai base_url."""
    mock_cls = MagicMock()
    mock_cls.return_value = MagicMock()

    with _mock_import_class(mock_cls)():
        create_llm({
            "provider": "openrouter",
            "model": "openai/gpt-4o",
            "api_key": "sk-test",
        })

    kwargs = mock_cls.call_args[1]
    assert kwargs.get("model") == "openai/gpt-4o"
    assert kwargs.get("base_url") == "https://openrouter.ai/api/v1"
    print("  openrouter → ChatOpenAI with openrouter base_url: OK")


def test_openai_compat_kwargs_passthrough():
    """max_tokens, top_p, api_key all pass through for OpenAI-compat providers."""
    for provider in ("deepseek", "qwen", "openrouter"):
        mock_cls = MagicMock()
        mock_cls.return_value = MagicMock()

        with _mock_import_class(mock_cls)():
            create_llm({
                "provider": provider,
                "model": "test-model",
                "api_key": "sk-test",
                "max_tokens": 1024,
                "top_p": 0.9,
            })

        kwargs = mock_cls.call_args[1]
        assert kwargs.get("api_key") == "sk-test", f"{provider}: api_key missing"
        assert kwargs.get("max_tokens") == 1024, f"{provider}: max_tokens missing"
        assert kwargs.get("top_p") == 0.9, f"{provider}: top_p missing"
    print("  openai-compat kwargs passthrough (deepseek, qwen, openrouter): OK")


if __name__ == "__main__":
    test_ollama_returns_chatollama()
    test_openai_returns_chatopenai()
    test_unknown_provider_raises()
    test_ollama_num_ctx_passed_through()
    test_openai_num_ctx_silently_dropped()
    test_callbacks_attached()
    test_ollama_unknown_kwarg_filtered()
    test_openai_unknown_kwarg_filtered()
    # Phase 2
    test_deepseek_returns_chatopenai()
    test_qwen_returns_chatopenai()
    test_openrouter_returns_chatopenai()
    test_openai_compat_kwargs_passthrough()
    print()
    print("=" * 50)
    print("All model factory tests passed.")
