"""Auto-discovery plugin system for MCP tool skills.

Each sibling module can define tools by decorating functions with @tool()
from ._registry.  No register(mcp) wrapper needed.
"""

import importlib
import pkgutil
import sys
import tomllib
from pathlib import Path

from src.config import skill_enabled
from . import _registry

_TOOLS_DIR = Path(__file__).resolve().parent


def _read_manifest(name: str) -> dict | None:
    """Parse <name>.toml if it exists, return the [skill] section."""
    toml_path = _TOOLS_DIR / f"{name}.toml"
    if not toml_path.exists():
        return None
    return tomllib.loads(toml_path.read_text()).get("skill", {})


def _build_tool_list() -> str:
    """Build the {tool_descriptions} string from enabled skills' prompt_hints."""
    lines = []
    for _, name, _ in pkgutil.iter_modules(__path__):
        if name in ("server", "_registry") or name.startswith("_"):
            continue
        if not skill_enabled(name):
            continue
        manifest = _read_manifest(name)
        if manifest and manifest.get("prompt_hint"):
            lines.append(manifest["prompt_hint"])
    return "\n".join(lines)


def skill_summary() -> list[dict]:
    """Return metadata for all known skills (API introspection endpoint)."""
    result = []
    for _, name, _ in pkgutil.iter_modules(__path__):
        if name in ("server", "_registry") or name.startswith("_"):
            continue
        manifest = _read_manifest(name)
        entry = {
            "name": name,
            "enabled": skill_enabled(name),
            "description": manifest.get("description", "") if manifest else "",
            "prompt_hint": manifest.get("prompt_hint", "") if manifest else "",
        }
        result.append(entry)
    return result


def register_all(mcp) -> None:
    """Import every enabled submodule, collect @tool() functions, register them.

    Uses importlib.reload() so that repeated calls (e.g. reload_tools())
    re-execute module-level @tool() decorators.  Skipped: "server" (the
    entry point), "_registry" (infrastructure), private modules starting
    with `_`, and modules disabled in config.
    """
    for _, name, _ in pkgutil.iter_modules(__path__):
        if name in ("server", "_registry") or name.startswith("_"):
            continue
        if not skill_enabled(name):
            continue

        full_name = f"{__package__ or __name__}.{name}"
        if full_name in sys.modules:
            importlib.reload(sys.modules[full_name])
        else:
            importlib.import_module(full_name)

    for fn, kwargs in _registry.collect():
        mcp.tool(**kwargs)(fn)
