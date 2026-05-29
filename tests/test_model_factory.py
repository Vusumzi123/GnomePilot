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


if __name__ == "__main__":
    test_ollama_returns_chatollama()
    test_openai_returns_chatopenai()
    test_unknown_provider_raises()
    test_ollama_num_ctx_passed_through()
    test_openai_num_ctx_silently_dropped()
    test_callbacks_attached()
    test_ollama_unknown_kwarg_filtered()
    test_openai_unknown_kwarg_filtered()
    print()
    print("=" * 50)
    print("All model factory tests passed.")
