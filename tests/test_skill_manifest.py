"""Tests for skill manifests (.toml) and prompt generation (Step 4)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools import _read_manifest, _build_tool_list, skill_summary


def test_manifests_exist():
    """Each skill module has a companion .toml with correct name."""
    for name in ("application", "package_manager", "window_manager", "vision"):
        m = _read_manifest(name)
        assert m is not None, f"Missing manifest for {name}"
        assert m.get("name") == name, f"name mismatch in {name}.toml"
        print(f"  {name}.toml: OK")


def test_all_enabled_builds_tool_list():
    """With all skills enabled, tool list includes app/pkg/window hints."""
    lines = _build_tool_list()
    assert "Open and close applications" in lines
    assert "Search packages" in lines
    assert "Move windows" in lines
    # Vision has empty prompt_hint — should not appear
    assert "capture" not in lines.lower()
    print("  all enabled tool list: OK")


def test_disabled_skill_omitted():
    """Temporarily disable package_manager, verify it's dropped."""
    import json
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    original = config_path.read_text()
    cfg = json.loads(original)
    cfg["skills"]["package_manager"] = False
    config_path.write_text(json.dumps(cfg, indent=2))

    lines = _build_tool_list()
    assert "Search packages" not in lines
    assert "Open and close applications" in lines
    assert "Move windows" in lines
    print("  disabled skill omitted: OK")

    config_path.write_text(original)


def test_skill_summary():
    """API introspection returns all known skills with status."""
    summary = skill_summary()
    names = [s["name"] for s in summary]
    assert len(summary) >= 4
    assert "application" in names
    assert "package_manager" in names
    assert "window_manager" in names
    assert "vision" in names
    assert all("enabled" in s for s in summary)
    assert all("description" in s for s in summary)
    print(f"  skill_summary: {len(summary)} skills: OK")
    for s in summary:
        print(f"    {s['name']}: enabled={s['enabled']} | {s.get('description','')[:40]}")


def test_missing_toml_graceful():
    """Skills without .toml still work (empty metadata)."""
    m = _read_manifest("nonexistent_skill")
    assert m is None
    print("  missing toml → None: OK")


def test_vision_empty_hint():
    """Vision skill has empty prompt_hint — doesn't appear in tool list."""
    m = _read_manifest("vision")
    assert m is not None
    assert m.get("prompt_hint") == ""
    lines = _build_tool_list()
    assert "vision" not in lines.lower() and "screen" not in lines.lower()
    print("  vision empty hint: OK")


def test_prompt_rendering():
    """Verify the prompt renders with actual tool descriptions."""
    from src.agents import Agents
    agents = Agents()
    prompt = agents.general_prompt
    assert "{tool_descriptions}" not in prompt, "Placeholder not replaced"
    assert "Open and close applications" in prompt
    assert "Search packages" in prompt
    assert "Move windows" in prompt
    print(f"  prompt rendered ({len(prompt)} chars): OK")
    # Show the tool list portion
    for line in prompt.split("\n"):
        if line.startswith("- "):
            print(f"    {line}")


if __name__ == "__main__":
    test_manifests_exist()
    test_all_enabled_builds_tool_list()
    test_disabled_skill_omitted()
    test_skill_summary()
    test_missing_toml_graceful()
    test_vision_empty_hint()
    test_prompt_rendering()
    print()
    print("=" * 50)
    print("All manifest tests passed.")
