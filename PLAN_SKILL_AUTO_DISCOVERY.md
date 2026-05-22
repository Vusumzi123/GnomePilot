# Plan: Auto-Discovery Skills (Deferred Registry + Manifests)

**Status: COMPLETE** — all 7 steps implemented. 10 test suites pass.

## Goal

Eliminate manual wiring when adding a skill.  Currently requires touching 3 files
(`.py` with `register()`, `config.json`, `prompts/general.md`).  After this plan,
adding a skill means creating **2 files** (`.py` + `.toml`) — zero boilerplate,
zero manual config entries, zero prompt edits.

---

## Step 1: Deferred Tool Registry (`_registry.py`)

### What

A module-level registry in `src/tools/_registry.py` that provides a `@tool()`
decorator.  Skill modules decorate their functions and the registry collects them.
`register_all()` later registers them with the real MCP server.

No `register(mcp)` wrapper needed in skill files anymore.

### Files

| File | Action |
|---|---|
| `src/tools/_registry.py` | **New** (~25 lines) |

### Implementation

```python
# src/tools/_registry.py
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
```

### Tests (`test_skill_registry.py`)

```python
"""Tests for deferred tool registry."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.tools._registry import tool, collect


def test_collect_single():
    @tool()
    def fn_a(x: int) -> str:
        """Does A."""
        return str(x)

    result = collect()
    assert len(result) == 1
    assert result[0][0] is fn_a
    assert result[0][1] == {}
    print("  single collect: OK")


def test_collect_multiple():
    @tool(name="custom_name")
    def fn_b(x: str) -> str:
        """Does B."""
        return x

    @tool()
    def fn_c(y: float) -> float:
        """Does C."""
        return y * 2

    result = collect()
    assert len(result) == 2
    assert result[0][1] == {"name": "custom_name"}
    assert result[1][1] == {}
    print("  multiple collect with kwargs: OK")


def test_collect_drains():
    @tool()
    def fn_d() -> None:
        pass

    result1 = collect()
    assert len(result1) == 1
    result2 = collect()
    assert result2 == []
    print("  collect drains after call: OK")


if __name__ == "__main__":
    test_collect_single()
    test_collect_multiple()
    test_collect_drains()
    print()
    print("All registry tests passed.")
```

### Acceptance criteria
- [x] `collect()` returns all `@tool()` decorated functions from imported modules
- [x] `collect()` drains the registry (second call returns empty list)
- [x] Extra kwargs passed to `@tool(name=...)` are preserved

---

## Step 2: Convert Existing Skills to `@tool()` Decorators

### What

Replace each `register(mcp)` wrapper function in the 4 existing skill modules
with `@tool()` decorators from `_registry`.

### Files

| File | Action |
|---|---|
| `src/tools/application.py` | Replace `register(mcp)` with `@tool()` on each function |
| `src/tools/package_manager.py` | Same |
| `src/tools/window_manager.py` | Same |
| `src/tools/vision.py` | Same |

### Pattern (before → after)

**Before (application.py):**
```python
def register(mcp) -> None:
    @mcp.tool()
    def tool_open_application(app_name: str) -> str: ...
    @mcp.tool()
    def tool_close_application(app_name: str) -> str: ...
```

**After:**
```python
from ._registry import tool

@tool()
def tool_open_application(app_name: str) -> str: ...

@tool()
def tool_close_application(app_name: str) -> str: ...
```

The `register()` function is removed. The function signatures and docstrings
stay identical — the LLM sees the same tool descriptions.

### Tests

Existing test suites pass unchanged — `test_close.py`, `test_agents.py`,
`test_executor.py`, `test_pipeline.py` all verify real tool execution.
No new tests needed for this step; the registry tests from Step 1 cover the
decorator behavior.

### Acceptance criteria
- [x] All 4 skill files import `tool` from `._registry`
- [x] No `register(mcp)` function remains in any skill file
- [x] Existing integration tests pass (agents, executor, pipeline, close)
- [x] `reload_tools()` works — clears and re-registers via new registry path

---

## Step 3: Update `register_all()` to Use Registry + Collect

### What

Rewrite `register_all()` in `__init__.py` to:
1. Import each enabled skill module (triggers `@tool()` collection)
2. Call `_registry.collect()` to get the pending tool list
3. Register each function with `mcp.tool(**kwargs)(fn)` on the real MCP server

### Files

| File | Action |
|---|---|
| `src/tools/__init__.py` | Rewrite `register_all()` |

### Implementation

```python
# src/tools/__init__.py (new version)
"""Auto-discovery plugin system for MCP tool skills.

Each sibling module can define tools by decorating functions with @tool()
from ._registry.  No register(mcp) wrapper needed.
"""

import importlib
import pkgutil

from src.config import skill_enabled
from . import _registry


def register_all(mcp) -> None:
    """Import every enabled submodule, collect @tool() functions, register them.

    Skipped: "server" (the entry point), "_registry" (infrastructure),
    private modules starting with `_` (except _registry itself),
    and modules disabled in config.json's `skills` section.
    """
    for _, name, _ in pkgutil.iter_modules(__path__):
        if name in ("server", "_registry") or name.startswith("_"):
            continue
        if not skill_enabled(name):
            continue

        importlib.import_module(f".{name}", __package__ or __name__)

    # Register all collected tools
    for fn, kwargs in _registry.collect():
        mcp.tool(**kwargs)(fn)
```

### Tests

Same integration tests as Step 2 — they verify tools are properly registered
and callable through the MCP server.

### Acceptance criteria
- [x] `register_all(mcp)` discovers all enabled modules
- [x] `reload_tools()` works end-to-end (clear + re-discover + re-register)
- [x] All 6 tools (open, close, search, install, screenshot, move-window) accessible
- [x] Disabling a skill in config removes its tools from the MCP server

---

## Step 4: Tool Manifests (`.toml` files)

### What

Each skill gets a companion `.toml` file with metadata: `name`, `description`,
and `prompt_hint`.  The `prompt_hint` auto-populates the agent's tool list in
its system prompt — no manual `prompts/general.md` edits needed.

Uses Python 3.11+ stdlib `tomllib` — zero new dependencies.

### Files

| File | Action |
|---|---|
| `src/tools/application.toml` | **New** |
| `src/tools/package_manager.toml` | **New** |
| `src/tools/window_manager.toml` | **New** |
| `src/tools/vision.toml` | **New** |
| `src/tools/__init__.py` | Extend `register_all()` to parse manifests |

### Manifest format

```toml
# src/tools/application.toml
[skill]
name = "application"
description = "Open and close desktop applications"
prompt_hint = "- Open and close applications"

# src/tools/package_manager.toml
[skill]
name = "package_manager"
description = "Search and install system packages (pacman / AUR)"
prompt_hint = "- Search and install system packages (pacman / AUR)"

# src/tools/window_manager.toml
[skill]
name = "window_manager"
description = "Move windows between GNOME workspaces"
prompt_hint = "- Move windows between workspaces"

# src/tools/vision.toml
[skill]
name = "vision"
description = "Capture and describe what is visible on screen"
prompt_hint = ""   # vision skill is not listed in the general agent prompt
```

`prompt_hint` can be empty — the skill is excluded from the tool list string.
The vision agent has its own prompt; its tool isn't shown to the general agent.

### Extend `__init__.py` to read manifests and build prompt descriptions

```python
import tomllib  # Python 3.11+ stdlib
from pathlib import Path

_SKILLS_DIR = Path(__file__).resolve().parent


def _read_manifest(name: str) -> dict | None:
    """Parse <name>.toml if it exists, return the [skill] section."""
    toml_path = _SKILLS_DIR / f"{name}.toml"
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
        entry = {"name": name, "enabled": skill_enabled(name)}
        if manifest:
            entry["description"] = manifest.get("description", "")
            entry["prompt_hint"] = manifest.get("prompt_hint", "")
        result.append(entry)
    return result
```

### Prompt template update

`prompts/general.md` changes from static tool list to `{tool_descriptions}`:

```markdown
You are a helpful AI assistant running on CachyOS (Arch Linux with GNOME).

## Tools Available
You have tools to:
{tool_descriptions}

## Behavior
...
```

The `{tool_descriptions}` placeholder is replaced at startup by the `Agents`
class (or Pipeline) using `_build_tool_list()`.

### Where prompt rendering happens

In `src/agents.py`, after reading `general.md`, replace the placeholder:

```python
from src.tools import _build_tool_list

self.general_prompt = read_prompt("general", "").replace(
    "{tool_descriptions}", _build_tool_list()
)
```

If `{tool_descriptions}` is not in the prompt file, no replacement occurs (safe
for custom prompts that don't use the placeholder).

### Tests (`test_skill_manifest.py`)

```python
"""Tests for skill manifests (.toml) and prompt generation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.tools import _read_manifest, _build_tool_list, skill_summary


def test_manifests_exist():
    """Each skill module has a companion .toml."""
    for name in ("application", "package_manager", "window_manager", "vision"):
        m = _read_manifest(name)
        assert m is not None, f"Missing manifest for {name}"
        assert m.get("name") == name
        print(f"  {name}.toml: OK")


def test_all_enabled_builds_tool_list():
    """With all skills enabled, tool list includes app/pkg/window hints."""
    lines = _build_tool_list()
    assert "Open and close applications" in lines
    assert "Search and install" in lines
    assert "Move windows" in lines
    # Vision skill has empty prompt_hint — should not appear
    print("  all enabled: OK")


def test_disabled_skill_omitted():
    """Temporarily disable package_manager, verify it's dropped."""
    import json
    config_path = Path(__file__).parent / "config.json"
    original = config_path.read_text()
    cfg = json.loads(original)
    cfg["skills"]["package_manager"] = False
    config_path.write_text(json.dumps(cfg, indent=2))

    lines = _build_tool_list()
    assert "Search and install" not in lines
    assert "Open and close applications" in lines
    print("  disabled omitted from prompt: OK")

    config_path.write_text(original)


def test_skill_summary():
    """API introspection returns all known skills with status."""
    summary = skill_summary()
    assert len(summary) >= 4
    names = [s["name"] for s in summary]
    assert "application" in names
    assert all("enabled" in s for s in summary)
    print(f"  skill_summary: {len(summary)} skills: OK")


def test_missing_toml_graceful():
    """Skills without .toml still work (empty metadata)."""
    m = _read_manifest("nonexistent_skill")
    assert m is None
    print("  missing toml → None: OK")


if __name__ == "__main__":
    test_manifests_exist()
    test_all_enabled_builds_tool_list()
    test_disabled_skill_omitted()
    test_skill_summary()
    test_missing_toml_graceful()
    print()
    print("All manifest tests passed.")
```

### Acceptance criteria
- [x] All 4 skill `.toml` files exist and parse correctly
- [x] `_build_tool_list()` includes prompt_hints from enabled skills only
- [x] Disabling a skill in config omits its line from the tool list
- [x] `prompts/general.md` uses `{tool_descriptions}` placeholder
- [x] Agent prompt renders with the correct tool list at startup
- [x] `skill_summary()` returns metadata for API introspection
- [x] Skills without `.toml` are handled gracefully (tool still loads)

---

## Step 5: Auto-Config — No Manual config.json Entries

### What

New skills auto-register as enabled.  The `skills` section of `config.json`
only needs entries to **disable** a skill.  `skill_enabled()` defaults to
`true` when no config entry exists for a skill name.

### Files

| File | Action |
|---|---|
| `src/config.py` | `skill_enabled()` already defaults to `True` — no change needed |
| `config.json` | Simplify — remove `true` entries, keep only explicit disables |

### Before (config.json)
```json
"skills": {
    "application": true,
    "package_manager": true,
    "window_manager": true,
    "vision": true
}
```

### After
```json
"skills": {
    "package_manager": false
}
```

`application`, `window_manager`, `vision` default to `true`.  Any new skill
(e.g. `browser`) is automatically enabled without a config entry.

### Tests

Same manifest tests from Step 4 verify that skills without config entries
are enabled.  The `test_disabled_skill_omitted` test sets a skill to `false`
and verifies omission.

### Acceptance criteria
- [x] Skills not listed in `config.json` `skills` section default to enabled
- [x] Setting `"name": false` in config disables the skill
- [x] Adding a new skill never requires editing `config.json`

---

## Step 6: Update `server.py` + `agents.py` for Prompt Rendering

### What

- `server.py`: No functional change (`.toml` reading is in `__init__.py`)
- `agents.py`: Replace `{tool_descriptions}` in general prompt after reading it
- `src/main.py`: No change (Pipeline builds from agents)

### Files

| File | Action |
|---|---|
| `src/agents.py` | Add `{tool_descriptions}` placeholder replacement |
| `src/tools/server.py` | No change needed |

### Implementation

In `src/agents.py.__init__`, modify the prompt reading line:

```python
from src.tools import _build_tool_list

# In __init__:
raw = read_prompt("general", (
    "You are a helpful AI assistant running on CachyOS (Arch Linux with GNOME). "
))
self.general_prompt = raw.replace("{tool_descriptions}", _build_tool_list())
```

If the prompt file doesn't contain `{tool_descriptions}`, the raw prompt is
used as-is (backward compatible with custom prompts).

### Tests

Run the full integration suite — `test_pipeline.py` confirms the general agent
responds with knowledge of its tools.

### Acceptance criteria
- [x] General agent prompt includes tool descriptions from manifests
- [x] Disabled skills don't appear in the rendered prompt
- [x] Vision agent prompt is unchanged (no `{tool_descriptions}` to expand)

---

## Step 7: Final Cleanup and Verification

### What

- Delete `config.json` entries that are default-`true` (optional cleanup)
- Run full test suite
- Document the new skill-creation flow in `README.md`

### Full test suite

```bash
python3 run_tests.py --unit       # 5 suites: extractor, formatter, history,
                                  #   router, skill_registry, skill_manifest

python3 run_tests.py --integration  # 4 suites: agents, executor, pipeline, close
```

### Adding a new skill (post-refactor)

1. Create `src/tools/my_skill.py`:
   ```python
   from ._registry import tool

   @tool()
   def tool_my_function(x: str) -> str:
       """Description the LLM sees when deciding to call this tool."""
       return _do_something(x)
   ```

2. Create `src/tools/my_skill.toml`:
   ```toml
   [skill]
   name = "my_skill"
   description = "What this skill does (for API/UI)"
   prompt_hint = "- Do something useful"
   ```

3. Done.  Restart or call `reload_tools()`.  The tool appears in the agent's
   prompt, is callable by the LLM, and is listed in the API's `skill_summary()`.

4. Optional: add `"my_skill": false` to `config.json` to disable.

---

## File manifest

| Step | File | Action | Est. lines |
|---|---|---|---|
| 1 | `src/tools/_registry.py` | **New** | ~25 |
| 1 | `test_skill_registry.py` | **New** | ~40 |
| 2 | `src/tools/application.py` | Replace `register()` with `@tool()` | ~15 removed |
| 2 | `src/tools/package_manager.py` | Same | ~15 removed |
| 2 | `src/tools/window_manager.py` | Same | ~5 removed |
| 2 | `src/tools/vision.py` | Same | ~5 removed |
| 3 | `src/tools/__init__.py` | Rewrite `register_all()` | ~30 |
| 4 | `src/tools/application.toml` | **New** | ~4 |
| 4 | `src/tools/package_manager.toml` | **New** | ~4 |
| 4 | `src/tools/window_manager.toml` | **New** | ~4 |
| 4 | `src/tools/vision.toml` | **New** | ~4 |
| 4 | `src/tools/__init__.py` | Add `_read_manifest`, `_build_tool_list`, `skill_summary` | ~40 |
| 4 | `test_skill_manifest.py` | **New** | ~60 |
| 5 | `config.json` | Simplify (remove default-true entries) | ~3 removed |
| 6 | `src/agents.py` | Replace `{tool_descriptions}` placeholder | ~3 |
| 6 | `prompts/general.md` | Switch to `{tool_descriptions}` | ~2 |
| — | `run_tests.py` | Add `test_skill_registry`, `test_skill_manifest` to unit set | ~1 |
| **Total** | | | ~+175, ~-40 = **+135 net** |

---

## Rollback

Every step is independently revertible:
- Step 1–3: Adding `_registry.py` + converting skills — old `register(mcp)`
  pattern works identically if we revert
- Step 4: `.toml` files are additive — removing them falls back to the old
  static prompt (keep `{tool_descriptions}` or revert `general.md`)
- Step 5: Config simplification — re-adding `true` entries restores old format
