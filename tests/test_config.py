"""Tests for src/config.py — config reader helpers."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config as config_module


def test_load_config_valid():
    cfg = config_module.load_config()
    assert isinstance(cfg, dict)
    assert "models" in cfg
    print("  load_config valid: OK")


def test_load_config_returns_default_on_missing():
    with patch.object(config_module, "CONFIG_PATH",
                      Path("/nonexistent/path/config.json")):
        cfg = config_module.load_config()
        assert cfg == config_module.DEFAULT_CONFIG
    print("  load_config missing → default: OK")


def test_load_config_returns_default_on_bad_json():
    from unittest.mock import mock_open
    with patch("builtins.open", mock_open(read_data="{invalid json {{{")):
        cfg = config_module.load_config()
        assert cfg == config_module.DEFAULT_CONFIG
    print("  load_config bad JSON → default: OK")


def test_unified_model_returns_none_when_not_set():
    with patch.object(config_module, "load_config", return_value={}):
        assert config_module.unified_model() is None
    print("  unified_model absent → None: OK")


def test_unified_model_returns_trimmed_value():
    with patch.object(config_module, "load_config",
                      return_value={"unified_model": "  qwen3.5:2b  "}):
        assert config_module.unified_model() == "qwen3.5:2b"
    print("  unified_model trimmed: OK")


def test_unified_model_handles_empty_string():
    with patch.object(config_module, "load_config",
                      return_value={"unified_model": ""}):
        assert config_module.unified_model() is None
    print("  unified_model empty → None: OK")


def test_get_setting_dotted_key_walk():
    with patch.object(config_module, "load_config", return_value={
        "orchestrator": {"temperature": 0.5, "chat_history_size": 20},
    }):
        assert config_module.get_setting("orchestrator.temperature") == 0.5
        assert config_module.get_setting("orchestrator.chat_history_size") == 20
    print("  get_setting dotted walk: OK")


def test_get_setting_missing_key_returns_default():
    with patch.object(config_module, "load_config", return_value={}):
        assert config_module.get_setting("nonexistent.key", 42) == 42
        assert config_module.get_setting("orchestrator.temperature") is None
    print("  get_setting missing → default: OK")


def test_screenshot_dir_returns_default_path():
    with patch.object(config_module, "load_config", return_value={}):
        path = config_module.screenshot_dir()
        assert path == Path("/tmp/os-assistant/screenshots")
    print("  screenshot_dir default: OK")


def test_screenshot_retention_default():
    with patch.object(config_module, "load_config", return_value={}):
        assert config_module.screenshot_retention() == 10
    print("  screenshot_retention default: OK")


def test_skill_enabled_defaults_true():
    with patch.object(config_module, "load_config", return_value={}):
        assert config_module.skill_enabled("package_manager") is True
        assert config_module.skill_enabled("nonexistent_skill") is True
    print("  skill_enabled defaults True: OK")


def test_skill_enabled_respects_config():
    with patch.object(config_module, "load_config", return_value={
        "skills": {"package_manager": False}
    }):
        assert config_module.skill_enabled("package_manager") is False
        assert config_module.skill_enabled("application") is True
    print("  skill_enabled respects config: OK")


def test_read_prompt_returns_content():
    content = config_module.read_prompt("general")
    assert isinstance(content, str)
    assert len(content) > 0
    assert "Tool" in content or "tool" in content
    print(f"  read_prompt general: OK ({len(content)} chars)")


def test_read_prompt_missing_returns_fallback():
    result = config_module.read_prompt("nonexistent_file_xyz", fallback="default text")
    assert result == "default text"
    print("  read_prompt missing → fallback: OK")


def test_install_guides_dir_creates_directory():
    with patch.object(config_module, "load_config", return_value={
        "install_guides": {"directory": "install_guides"}
    }):
        path = config_module.install_guides_dir()
        expected = config_module.PROJECT_DIR / "install_guides"
        assert path == expected
        assert path.exists()
    print("  install_guides_dir creates dir: OK")


def test_install_guides_dir_reads_per_skill_config():
    """When config.json has no install_guides, fall back to package_manager/config.toml."""
    with patch.object(config_module, "load_config", return_value={}):
        path = config_module.install_guides_dir()
        expected = config_module.PROJECT_DIR / "install_guides"
        assert path == expected
        assert path.exists()
    print("  install_guides_dir per-skill fallback: OK")


def test_mcp_required_env_keys():
    """Verify MCP_ENV_KEYS includes all vars required for GUI app launch.

    Canary test — if someone removes a key from MCP_ENV_KEYS without
    removing it from this test, it fails. Prevents the display-vars-
    missing bug (apps silently fail to open via MCP pipeline).
    """
    from src.agents import MCP_ENV_KEYS

    required = {
        "PATH", "HOME",
        "DBUS_SESSION_BUS_ADDRESS",
        "DISPLAY", "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
        "XDG_CURRENT_DESKTOP", "LANG",
    }
    keys = set(MCP_ENV_KEYS)
    missing = required - keys
    assert not missing, f"Missing required keys from MCP_ENV_KEYS: {missing}"
    assert len(MCP_ENV_KEYS) == len(keys), \
        f"Duplicate keys in MCP_ENV_KEYS: {sorted(MCP_ENV_KEYS)}"
    print("  MCP_ENV_KEYS: all required + no dupes: OK")


# ── model_config / unified_model_config tests ──


def test_model_config_string():
    """String model value → normalized to {provider: ollama, model: ...}."""
    with patch.object(config_module, "load_config", return_value={
        "models": {"orchestrator": "llama3.1:8b"}
    }):
        cfg = config_module.model_config("orchestrator")
        assert cfg == {"provider": "ollama", "model": "llama3.1:8b"}
    print("  model_config string normalized: OK")


def test_model_config_object():
    """Object model value → passed through, default provider = ollama."""
    with patch.object(config_module, "load_config", return_value={
        "models": {
            "orchestrator": {"provider": "openai", "model": "gpt-4o",
                             "api_key": "sk-test"}
        }
    }):
        cfg = config_module.model_config("orchestrator")
        assert cfg["provider"] == "openai"
        assert cfg["model"] == "gpt-4o"
        assert cfg["api_key"] == "sk-test"
    print("  model_config object passed through: OK")


def test_model_config_object_defaults_provider():
    """Object without provider → defaults to ollama."""
    with patch.object(config_module, "load_config", return_value={
        "models": {"vision": {"model": "minicpm-v:8b"}}
    }):
        cfg = config_module.model_config("vision")
        assert cfg == {"provider": "ollama", "model": "minicpm-v:8b"}
    print("  model_config object defaults provider: OK")


def test_model_config_missing():
    """Missing key → returns default Ollama config."""
    with patch.object(config_module, "load_config", return_value={}):
        cfg = config_module.model_config("orchestrator")
        assert cfg["provider"] == "ollama"
        assert "model" in cfg
    print("  model_config missing → default: OK")


def test_unified_model_config_string():
    """String unified_model → normalized."""
    with patch.object(config_module, "load_config", return_value={
        "unified_model": "qwen3.5:9b"
    }):
        cfg = config_module.unified_model_config()
        assert cfg == {"provider": "ollama", "model": "qwen3.5:9b"}
    print("  unified_model_config string: OK")


def test_unified_model_config_object():
    """Object unified_model → passed through."""
    with patch.object(config_module, "load_config", return_value={
        "unified_model": {"provider": "openai", "model": "gpt-4o",
                          "api_key": "sk-test"}
    }):
        cfg = config_module.unified_model_config()
        assert cfg["provider"] == "openai"
        assert cfg["model"] == "gpt-4o"
    print("  unified_model_config object: OK")


def test_unified_model_config_null():
    """null unified_model → None."""
    with patch.object(config_module, "load_config", return_value={
        "unified_model": None
    }):
        assert config_module.unified_model_config() is None
    print("  unified_model_config null → None: OK")


def test_unified_model_config_missing():
    """Missing unified_model key → None."""
    with patch.object(config_module, "load_config", return_value={}):
        assert config_module.unified_model_config() is None
    print("  unified_model_config missing → None: OK")


# ── bootstrap tests ──


def test_bootstrap_creates_if_missing():
    """No config.json → file created with default content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch CONFIG_PATH to a temp location
        fake_path = Path(tmpdir) / "config.json"
        with patch.object(config_module, "CONFIG_PATH", fake_path):
            assert not fake_path.exists()
            result = config_module.bootstrap_config_if_missing()
            assert result is True
            assert fake_path.exists()
            # Verify it's valid JSON with expected keys
            cfg = config_module.load_config()
            assert "models" in cfg
            assert "orchestrator" in cfg
    print("  bootstrap creates config: OK")


def test_bootstrap_skips_if_exists():
    """Existing config.json → no change."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_path = Path(tmpdir) / "config.json"
        fake_path.write_text('{"custom": true}')
        with patch.object(config_module, "CONFIG_PATH", fake_path):
            result = config_module.bootstrap_config_if_missing()
            assert result is False
            assert fake_path.read_text() == '{"custom": true}'
    print("  bootstrap skips if exists: OK")


def test_bootstrap_default_content():
    """Generated config matches expected structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_path = Path(tmpdir) / "config.json"
        with patch.object(config_module, "CONFIG_PATH", fake_path):
            config_module.bootstrap_config_if_missing()
            cfg = config_module.load_config()
            # Verify key sections exist
            assert cfg["models"]["orchestrator"] == "llama3.1:8b"
            assert cfg["models"]["vision"] == "minicpm-v:8b"
            assert cfg["unified_model"] is None
            assert cfg["orchestrator"]["temperature"] == 0
            assert cfg["orchestrator"]["num_ctx"] == 32768
            # install_guides should NOT be in the default — handled by fallback
            assert "install_guides" not in cfg
    print("  bootstrap default content: OK")


if __name__ == "__main__":
    test_load_config_valid()
    test_load_config_returns_default_on_missing()
    test_load_config_returns_default_on_bad_json()
    test_unified_model_returns_none_when_not_set()
    test_unified_model_returns_trimmed_value()
    test_unified_model_handles_empty_string()
    test_get_setting_dotted_key_walk()
    test_get_setting_missing_key_returns_default()
    test_screenshot_dir_returns_default_path()
    test_screenshot_retention_default()
    test_skill_enabled_defaults_true()
    test_skill_enabled_respects_config()
    test_read_prompt_returns_content()
    test_read_prompt_missing_returns_fallback()
    test_install_guides_dir_creates_directory()
    test_install_guides_dir_reads_per_skill_config()
    test_mcp_required_env_keys()
    # New multi-provider tests
    test_model_config_string()
    test_model_config_object()
    test_model_config_object_defaults_provider()
    test_model_config_missing()
    test_unified_model_config_string()
    test_unified_model_config_object()
    test_unified_model_config_null()
    test_unified_model_config_missing()
    test_bootstrap_creates_if_missing()
    test_bootstrap_skips_if_exists()
    test_bootstrap_default_content()
    print()
    print("=" * 50)
    print("All config tests passed.")
