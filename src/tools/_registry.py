"""Deferred tool registry — skills decorate with @tool(), register_all() wires them
to the real MCP server at startup.  No per-skill register(mcp) boilerplate needed."""

from __future__ import annotations
from typing import Callable

_PENDING: list[tuple[Callable, dict]] = []


def tool(**kwargs):
    """Deferred @tool() decorator.  Collects the function for later MCP registration.

    Usage in a skill file (e.g. browser.py):
        from ._registry import tool

        @tool()
        def tool_open_tab(url: str) -> str:
            '''Open a URL in the default browser.'''
            ...

    The function's docstring becomes the tool description visible to the LLM.
    """
    def decorator(fn):
        _PENDING.append((fn, kwargs))
        return fn
    return decorator


def collect() -> list[tuple[Callable, dict]]:
    """Return and drain pending tools.  Called by register_all() after
    importing all enabled skill modules."""
    result = list(_PENDING)
    _PENDING.clear()
    return result
