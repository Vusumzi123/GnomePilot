"""Auto-discovery plugin system for MCP tool skills.

Each sibling module can optionally export a `register(mcp: FastMCP)` function.
`register_all()` discovers and invokes them automatically, filtering by the
`skills` section of config.json — no manual wiring needed.
"""

import importlib
import pkgutil

from src.config import skill_enabled


def register_all(mcp) -> None:
    """Import every submodule of this package and call its `register(mcp)` if defined
    AND enabled in config.json's `skills` section.

    Skipped: "server" (the entry point), private modules starting with `_`,
    and modules with `skills.<name>: false` in config.
    """
    for _, name, _ in pkgutil.iter_modules(__path__):
        if name in ("server",) or name.startswith("_"):
            continue
        if not skill_enabled(name):
            continue

        module = importlib.import_module(f".{name}", __package__ or __name__)
        register_fn = getattr(module, "register", None)
        if callable(register_fn):
            register_fn(mcp)
