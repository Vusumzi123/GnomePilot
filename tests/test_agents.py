"""Tests for src/agents.py — requires Ollama running for integration tests."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Unit tests (no Ollama needed) ──


def test_string_config_creates_chatollama():
    """Default string config → create_llm called with ollama provider."""
    mock_llm = MagicMock()

    with patch("src.agents.create_llm", return_value=mock_llm) as mock_factory:
        with patch("src.agents.model_config") as mock_mc:
            with patch("src.agents.unified_model_config", return_value=None):
                with patch("src.agents.debug_enabled", return_value=False):
                    mock_mc.side_effect = lambda role: {
                        "provider": "ollama", "model": f"test-{role}"
                    }
                    from src.agents import Agents
                    a = Agents()

                    # All three LLMs created via factory
                    assert mock_factory.call_count == 3
                    # Check provider is ollama
                    for call_args in mock_factory.call_args_list:
                        cfg = call_args[0][0]
                        assert cfg["provider"] == "ollama"

    print("  string config → ollama provider: OK")


def test_openai_config_creates_chatopenai():
    """OpenAI config → create_llm called with openai provider."""
    mock_llm = MagicMock()

    with patch("src.agents.create_llm", return_value=mock_llm) as mock_factory:
        with patch("src.agents.model_config") as mock_mc:
            with patch("src.agents.unified_model_config", return_value=None):
                with patch("src.agents.debug_enabled", return_value=False):
                    mock_mc.side_effect = lambda role: {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "api_key": "sk-test",
                    }
                    from src.agents import Agents
                    a = Agents()

                    assert mock_factory.call_count == 3
                    for call_args in mock_factory.call_args_list:
                        cfg = call_args[0][0]
                        assert cfg["provider"] == "openai"

    print("  openai config → openai provider: OK")


def test_unified_overrides_all_roles():
    """unified_model set → all three LLMs use same config."""
    mock_llm = MagicMock()
    unified_cfg = {"provider": "openai", "model": "gpt-4o", "api_key": "sk-u"}

    with patch("src.agents.create_llm", return_value=mock_llm) as mock_factory:
        with patch("src.agents.unified_model_config", return_value=unified_cfg):
            with patch("src.agents.debug_enabled", return_value=False):
                from src.agents import Agents
                a = Agents()

                assert mock_factory.call_count == 3
                # All three calls should use the same config (router gets extra stop/temp)
                first_cfg = mock_factory.call_args_list[0][0][0]
                second_cfg = mock_factory.call_args_list[1][0][0]
                assert first_cfg["provider"] == "openai"
                assert first_cfg["model"] == "gpt-4o"
                assert second_cfg["provider"] == "openai"
                assert second_cfg["model"] == "gpt-4o"

    print("  unified overrides all roles: OK")


async def test_shutdown_skips_ollama_when_not_in_use():
    """No ollama provider → shutdown is a no-op (no ollama import)."""
    mock_llm = MagicMock()
    with patch("src.agents.create_llm", return_value=mock_llm):
        with patch("src.agents.model_config") as mock_mc:
            with patch("src.agents.unified_model_config", return_value=None):
                with patch("src.agents.debug_enabled", return_value=False):
                    mock_mc.side_effect = lambda role: {
                        "provider": "openai",
                        "model": "gpt-4o",
                        "api_key": "sk-test",
                    }
                    from src.agents import Agents
                    a = Agents()
                    assert a._active_providers == {"openai"}
                    # shutdown should return immediately without importing ollama
                    await a.shutdown()
                    # If we got here without error, the test passes
    print("  shutdown skips ollama when not in use: OK")


# ── Integration tests (need Ollama running) ──


async def test_construction():
    """Agents can be constructed without Ollama."""
    from src.agents import Agents
    a = Agents()
    assert a.general_llm is not None
    assert a.general is None  # not started yet
    assert a.vision is None
    assert len(a.general_prompt) > 0
    assert len(a.vision_prompt) > 0
    print("  construction: OK")


async def test_start_and_agents():
    """After start(), both agents are non-None."""
    from src.agents import Agents
    a = Agents()
    await a.start()

    gen = a.general
    vis = a.vision
    assert gen is not None, "General agent not created"
    assert vis is not None, "Vision agent not created"

    print(f"  start(): general_agent={type(gen).__name__}, vision_agent={type(vis).__name__}")
    print("  agents created: OK")

    await a.shutdown()


async def test_shutdown():
    """Shutdown unloads models without error."""
    from src.agents import Agents
    a = Agents()
    await a.start()
    await a.shutdown()
    print("  shutdown() no errors: OK")


async def main():
    # Unit tests (no Ollama)
    test_string_config_creates_chatollama()
    test_openai_config_creates_chatopenai()
    test_unified_overrides_all_roles()
    await test_shutdown_skips_ollama_when_not_in_use()

    # Integration tests (need Ollama)
    await test_construction()
    await test_start_and_agents()
    await test_shutdown()

    print()
    print("=" * 50)
    print("All Agents tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
