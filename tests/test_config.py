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
    print()
    print("=" * 50)
    print("All config tests passed.")
