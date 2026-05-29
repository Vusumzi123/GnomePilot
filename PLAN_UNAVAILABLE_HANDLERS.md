# Plan: Unavailable Handlers for Toggleable Skills

## Goal

When a skill is disabled via its `config.toml` and the assistant is asked to use it,
the user gets a clear "not available" message instead of a silent hang. The handler
logic lives in each skill's own `__init__.py` and the message is configurable via
`manifest.toml`.

## Current State

| Skill | Agent/Sub-tool | Disabled behavior | Needs stub? |
|-------|---------------|-------------------|-------------|
| **vision** | Own agent (router can route to it) | Agent has 0 tools but prompt says "use screenshot tool" → LLM tries to call non-existent tool → **hangs** | **YES** (today) |
| **application** | Sub-tool of general agent | `{tool_descriptions}` omits it → LLM doesn't know about it → natural response | No (today) |
| **package_manager** | Sub-tool of general agent | Same — dynamic prompt excludes it | No (today) |
| **web_search** | Sub-tool of general agent | Same — dynamic prompt excludes it | No (today) |
| **window_manager** | Sub-tool of general agent | Same — dynamic prompt excludes it | No (today) |

The distinction: `vision` has its **own agent** in `agents.py` with a hardcoded `prompts/vision.md`.
The Router can route directly to `["vision"]`. When disabled, the agent still exists but has 0 tools.
The other 4 skills are sub-tools of the general agent whose prompt is dynamically built.

**Why this matters**: today only `vision` has a hang risk. But if any other skill
becomes a standalone agent in the future, the same thing will happen. Adding handlers
to all skills now prevents the bug from recurring later.

## Target State

Every skill's `__init__.py` exports a `handler` async callable:

```
src/tools/vision/__init__.py           → exports handler (used by agents.py when disabled)
src/tools/application/__init__.py      → exports handler (ready for when it becomes its own agent)
src/tools/package_manager/__init__.py  → exports handler (ready)
src/tools/web_search/__init__.py       → exports handler (ready)
src/tools/window_manager/__init__.py   → exports handler (ready)
```

The message text is loaded from each skill's `manifest.toml`:

```toml
[skill]
name = "vision"
description = "..."
prompt_hint = "..."
unavailable_message = "I cannot see your screen right now — the vision/screenshot capability is not enabled."
```

`agents.py` imports every handler at startup. When a skill-specific agent has no tools,
it substitutes the handler instead of creating a crippled LangGraph agent.

## Phases

---

### Phase 1: Add handlers to all 5 skills

**Files to modify per skill:**

| Skill | `__init__.py` change | `manifest.toml` change |
|-------|---------------------|----------------------|
| `vision` | Add `handler` function + manifest-based message loader | Add `unavailable_message` field |
| `application` | Add `handler` function + manifest-based message loader | Add `unavailable_message` field |
| `package_manager` | Add `handler` function + manifest-based message loader | Add `unavailable_message` field |
| `web_search` | Add `handler` function + manifest-based message loader | Add `unavailable_message` field |
| `window_manager` | Add `handler` function + manifest-based message loader | Add `unavailable_message` field |

**Pattern (identical for every skill):**

In `src/tools/<name>/__init__.py`, add at the top after imports:

```python
import tomllib
from pathlib import Path
from langchain_core.messages import AIMessage

_HERE = Path(__file__).parent
_UNAVAILABLE_MSG = "<skill-name> is not enabled."

_try_manifest = _HERE / "manifest.toml"
if _try_manifest.exists():
    try:
        _UNAVAILABLE_MSG = tomllib.loads(_try_manifest.read_text()).get(
            "skill", {}).get("unavailable_message", _UNAVAILABLE_MSG)
    except Exception:
        pass


async def handler(input, config=None):
    """Returned when the skill is disabled — provides a clear unavailable message."""
    return {"messages": [AIMessage(content=_UNAVAILABLE_MSG)]}
```

Default messages per skill:

| Skill | Default `_UNAVAILABLE_MSG` |
|-------|---------------------------|
| `vision` | `"I cannot see your screen right now — the vision/screenshot capability is not enabled."` |
| `application` | `"I cannot open or close applications right now — the application tools are not enabled."` |
| `package_manager` | `"I cannot search or install packages right now — the package management tools are not enabled."` |
| `web_search` | `"I cannot search the web right now — the web search tool is not enabled."` |
| `window_manager` | `"I cannot move windows between workspaces right now — the window management tools are not enabled."` |

In each `manifest.toml`, add:

```toml
[skill]
name = "..."
description = "..."
prompt_hint = "..."
unavailable_message = "..."   # <-- overrides the code default
```

**Implementation note:** The `handler` export and `_UNAVAILABLE_MSG` constant live in
`__init__.py` alongside the existing `@tool()` functions. The `handler` is always
importable regardless of whether the skill is enabled (`register_all` skipping the
import doesn't matter — `agents.py` imports directly, not through `register_all`).

**Subagent delegation:** `python-expert`

**Manual testing per skill:**

```bash
# After Phase 1, each skill's handler should be importable and callable
source .venv/bin/activate
python3 -c "
import asyncio
from src.tools.vision import handler as vh
from src.tools.application import handler as ah

async def test():
    v = await vh({}, None)
    a = await ah({}, None)
    print('vision handler:', v['messages'][0].content[:60])
    print('application handler:', a['messages'][0].content[:60])

asyncio.run(test())
"
# Expected: both return their unavailable messages
```

---

### Phase 2: Wire handlers in agents.py

**File: `src/agents.py`**

Currently:
```python
tools = await self._client.get_tools()

vision_tools = [t for t in tools if t.name == "tool_capture_screen"]
general_tools = [t for t in tools if t.name != "tool_capture_screen"]

self._general_agent = create_react_agent(
    self._general_llm, general_tools, prompt=self.general_prompt,
)
self._vision_agent = create_react_agent(
    self._vision_llm, vision_tools, prompt=self.vision_prompt,
)
```

After change:

```python
from src.tools.vision import handler as _vision_handler
from src.tools.application import handler as _application_handler
from src.tools.package_manager import handler as _package_manager_handler
from src.tools.web_search import handler as _web_search_handler
from src.tools.window_manager import handler as _window_manager_handler

# ... (inside start() after get_tools) ...

vision_tools = [t for t in tools if t.name == "tool_capture_screen"]
general_tools = [t for t in tools if t.name != "tool_capture_screen"]

self._general_agent = create_react_agent(
    self._general_llm, general_tools, prompt=self.general_prompt,
)

if not vision_tools:
    self._vision_agent = _vision_handler
else:
    self._vision_agent = create_react_agent(
        self._vision_llm, vision_tools, prompt=self.vision_prompt,
    )
```

**Note:** Only `vision` is wired as an agent today. The other 4 handlers are imported
but not yet used — `agents.py` only has `general` and `vision` agent slots. When/if
any skill becomes a standalone agent, the wiring is a copy-paste of the vision pattern:

```python
# Future example — when web_search becomes its own agent:
if not web_search_tools:
    self._web_search_agent = _web_search_handler
else:
    self._web_search_agent = create_react_agent(...)
```

**Subagent delegation:** `python-expert`

**Manual testing:**

```bash
# Disable vision, verify handler is used
source .venv/bin/activate

# 1. Disable vision
cp src/tools/vision/config.toml /tmp/vision_cfg.bak
echo -e "[skill]\nenabled = false" > src/tools/vision/config.toml

# 2. Run the assistant and ask a screen question
python3 -c "
import asyncio
from src.agents import Agents

async def test():
    a = Agents()
    await a.start()
    agent = a.vision
    
    # Verify it's the handler (not a CompiledGraph)
    result = await agent({'messages': []}, None)
    msgs = result['messages']
    if msgs:
        print('Vision agent response:', msgs[0].content[:80])
    await a.shutdown()

asyncio.run(test())
"
# Expected: "I cannot see your screen right now — the vision/screenshot capability is not enabled."

# 3. Restore vision
mv /tmp/vision_cfg.bak src/tools/vision/config.toml
```

---

### Phase 3: Tests + final verification

**New test file: `tests/test_handlers.py`** (unit tests, no Ollama needed)

```python
"""Tests for skill unavailable handlers."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.vision import handler as vision_handler
from src.tools.application import handler as application_handler
from src.tools.package_manager import handler as package_manager_handler
from src.tools.web_search import handler as web_search_handler
from src.tools.window_manager import handler as window_manager_handler


async def test_all_handlers_return_message():
    handlers = {
        "vision": vision_handler,
        "application": application_handler,
        "package_manager": package_manager_handler,
        "web_search": web_search_handler,
        "window_manager": window_manager_handler,
    }
    for name, fn in handlers.items():
        result = await fn({}, None)
        msgs = result.get("messages", [])
        assert len(msgs) == 1, f"{name}: expected 1 message, got {len(msgs)}"
        text = msgs[0].content
        assert len(text) > 20, f"{name}: message too short: {text!r}"
        print(f"  {name}: {text[:60]}...")


async def test_vision_handler_routes_through_agents():
    """Disable vision, verify agents.py wires the handler as vision agent."""
    from src.agents import Agents

    # Temporarily disable vision
    cfg_path = Path("src/tools/vision/config.toml")
    backup = cfg_path.read_text()
    cfg_path.write_text("[skill]\nenabled = false\n")

    try:
        a = Agents()
        await a.start()
        result = await a.vision({"messages": []}, None)
        msgs = result.get("messages", [])
        assert len(msgs) == 1
        assert "cannot" in msgs[0].content.lower()
        print("  vision disabled → handler wired: OK")
        await a.shutdown()
    finally:
        cfg_path.write_text(backup)


async def main():
    await test_all_handlers_return_message()
    await test_vision_handler_routes_through_agents()
    print()
    print("=" * 50)
    print("All handler tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
```

**Run existing test suite to verify no regressions:**

```bash
python3 run_tests.py --unit
# Expected: 12/12 pass (new handlers test included)

python3 run_tests.py --integration
# Expected: 4/4 pass
```

**Subagent delegation:**
- `ai-integration` — Run full test suite, verify no regressions
- `security-expert` — Review handler pattern: no import-time side effects (`@tool()` decorators must NOT fire from handler imports), no config disclosure through message content

**Manual smoke test:**

```bash
# 1. Disable vision, run assistant, verify clear message
cp src/tools/vision/config.toml /tmp/vision_cfg.bak
echo -e "[skill]\nenabled = false" > src/tools/vision/config.toml
python3 -m src.main
# Type: "look at my screen"
# Expected: "I cannot see your screen right now — the vision/screenshot capability is not enabled."
# Type: "what can you see"
# Expected: Same unavailable message (LLM router fallback)
# Type: "look at my screen and open firefox"
# Expected: Vision unavailable message + Firefox opens (chain case)
mv /tmp/vision_cfg.bak src/tools/vision/config.toml

# 2. Re-enable vision, verify it works
python3 -m src.main
# Type: "what is on my screen"
# Expected: Screenshot is captured and described
```

---

### Phase 4: Documentation

**File: `AGENTS.md`**

Add to "Skill system" section after "Adding a skill":

```markdown
### Unavailable handler
Every skill `__init__.py` must export an `async def handler(input, config=None)`.
It returns `{"messages": [AIMessage(content="...")]}` when the skill is disabled.
The message text is loaded from `manifest.toml` `[skill] unavailable_message`,
falling back to a hardcoded default in `__init__.py`.

When a skill becomes a standalone agent, wire it in `src/agents.py`:
```python
from src.tools.<name> import handler as _<name>_handler
if not <name>_tools:
    self._<name>_agent = _<name>_handler
```
```

**File: `EXECUTIVE_SUMMARY.md`** — regenerated per change-cycle rule.

---

## Full list of files touched

| File | Phase | Action |
|------|-------|--------|
| `src/tools/vision/__init__.py` | 1 | Add `handler` + manifest message loader |
| `src/tools/vision/manifest.toml` | 1 | Add `unavailable_message` field |
| `src/tools/application/__init__.py` | 1 | Add `handler` + manifest message loader |
| `src/tools/application/manifest.toml` | 1 | Add `unavailable_message` field |
| `src/tools/package_manager/__init__.py` | 1 | Add `handler` + manifest message loader |
| `src/tools/package_manager/manifest.toml` | 1 | Add `unavailable_message` field |
| `src/tools/web_search/__init__.py` | 1 | Add `handler` + manifest message loader |
| `src/tools/web_search/manifest.toml` | 1 | Add `unavailable_message` field |
| `src/tools/window_manager/__init__.py` | 1 | Add `handler` + manifest message loader |
| `src/tools/window_manager/manifest.toml` | 1 | Add `unavailable_message` field |
| `src/agents.py` | 2 | Import all 5 handlers; wire vision handler when `vision_tools` empty |
| `tests/test_handlers.py` | 3 | New: 2 async tests |
| `AGENTS.md` | 4 | Add "Unavailable handler" section |
| `EXECUTIVE_SUMMARY.md` | 4 | Regenerated |

## Verification checklist

- [ ] All 5 skill `__init__.py` files have `handler` export
- [ ] All 5 `manifest.toml` files have `unavailable_message` field
- [ ] `_UNAVAILABLE_MSG` default in each `__init__.py` is skill-specific
- [ ] Handler imports in `agents.py` do NOT trigger `@tool()` registration (`handler` is a plain function, no `@tool()` decorator)
- [ ] `register_all()` still skips disabled skills (no change to discovery/registration)
- [ ] `_build_tool_list()` still omits disabled skills from `{tool_descriptions}` (no change)
- [ ] Disabled vision → handler responds instead of hanging
- [ ] Enabled vision → screenshot still works
- [ ] Disabled general sub-tools → `{tool_descriptions}` dynamically excludes them, LLM doesn't mention them, no hang
- [ ] 12/12 unit tests pass
- [ ] 4/4 integration tests pass
