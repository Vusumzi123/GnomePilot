"""Auto-discovery plugin system for MCP tool skills.

Each sibling module can define tools by decorating functions with @tool()
from ._registry.  No register(mcp) wrapper needed.
"""

import importlib
import pkgutil
import sys

from src.config import skill_enabled
from . import _registry


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
