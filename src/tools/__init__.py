"""Auto-discovery plugin system for MCP tool skills.

Each skill lives in its own subdirectory under src/tools/ with:
  - __init__.py    — tool functions, decorated with @tool() from ._registry
  - manifest.toml  — [skill] name, description, prompt_hint
  - config.toml    — [skill] enabled=true/false (optional, defaults to true)

Shared helpers (desktop_index.py, fuzzy_match.py) stay flat — they have no
@tool() decorators and are naturally excluded by the manifest.toml check.
"""

import importlib
import sys
import tomllib
from pathlib import Path

from src.config import load_config
from . import _registry

_TOOLS_DIR = Path(__file__).resolve().parent


# ── discovery ──

def _discover_skills() -> list[str]:
    """Return sorted names of skill packages (dirs containing manifest.toml).

    Filters out:
      - Files (flat modules like desktop_index.py)
      - Private dirs (names starting with "_")
      - Dirs without manifest.toml
    """
    skills = []
    for entry in _TOOLS_DIR.iterdir():
        if not entry.is_dir():
            continue
        if entry.name.startswith("_"):
            continue
        if not (entry / "manifest.toml").exists():
            continue
        skills.append(entry.name)
    return sorted(skills)


# ── manifest ──

def _read_manifest(name: str) -> dict | None:
    """Parse <name>/manifest.toml if it exists, return the [skill] section."""
    toml_path = _TOOLS_DIR / name / "manifest.toml"
    if not toml_path.exists():
        return None
    try:
        return tomllib.loads(toml_path.read_text()).get("skill", {})
    except Exception:
        return None


# ── per-skill config ──

def _read_skill_config(name: str) -> dict:
    """Read per-skill config from <name>/config.toml, return [skill] section."""
    config_path = _TOOLS_DIR / name / "config.toml"
    if not config_path.exists():
        return {}
    try:
        return tomllib.loads(config_path.read_text()).get("skill", {})
    except Exception:
        return {}


def _is_skill_enabled(name: str) -> bool:
    """Whether a skill is loaded.  Checks in order:

    1. config.json ``skills.<name>`` override (backward compat)
    2. Skill's own config.toml ``[skill] enabled``
    3. Defaults to True
    """
    cfg = load_config()
    if name in cfg.get("skills", {}):
        return bool(cfg["skills"][name])
    sc = _read_skill_config(name)
    return sc.get("enabled", True)


# ── tool description builder ──

def _build_tool_list() -> str:
    """Build the {tool_descriptions} string from enabled skills' prompt_hints."""
    lines = []
    for name in _discover_skills():
        if not _is_skill_enabled(name):
            continue
        manifest = _read_manifest(name)
        if manifest and manifest.get("prompt_hint"):
            lines.append(manifest["prompt_hint"])
    return "\n".join(lines)


# ── introspection ──

def skill_summary() -> list[dict]:
    """Return metadata for all known skills (API introspection endpoint)."""
    result = []
    for name in _discover_skills():
        manifest = _read_manifest(name)
        entry = {
            "name": name,
            "enabled": _is_skill_enabled(name),
            "description": manifest.get("description", "") if manifest else "",
            "prompt_hint": manifest.get("prompt_hint", "") if manifest else "",
        }
        result.append(entry)
    return result


# ── MCP registration ──

def register_all(mcp) -> None:
    """Import every enabled skill package, collect @tool() functions,
    register them on the FastMCP server.

    Uses importlib.reload() so that repeated calls (e.g. reload_tools())
    re-execute module-level @tool() decorators.
    """
    for name in _discover_skills():
        if not _is_skill_enabled(name):
            continue

        full_name = f"{__package__ or __name__}.{name}"
        if full_name in sys.modules:
            importlib.reload(sys.modules[full_name])
        else:
            importlib.import_module(full_name)

    for fn, kwargs in _registry.collect():
        mcp.tool(**kwargs)(fn)
