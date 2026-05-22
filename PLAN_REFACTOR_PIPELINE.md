# Plan: Pipeline Architecture Refactor

**Status: COMPLETE** — all 4 phases implemented.  8 test suites, 7 domain classes.

## Goal

Replace `Orchestrator` (360-line god class) with a Pipeline of single-responsibility
classes, each independently testable and reusable by a future HTTP API.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Pipeline                           │
│                                                      │
│  Context ──► Enrich ──► Route ──► Build ──► Execute │
│                           (History)                  │
│               (History     (Router)   (History       │
│                .enrich)               .build)        │
│                                                      │
│  Result ◄── Store ◄── Format ◄── Extract ◄──────────│
│            (History) (Formatter) (Extractor)         │
└──────────────────────────────────────────────────────┘
```

### Class Map

| Class | File | Responsibility | Depends on |
|---|---|---|---|
| `History` | `src/history.py` | chat turns, message building, enrichment | `chat_history_size` config |
| `Formatter` | `src/formatter.py` | regex cleanup of LLM output | `re` (stdlib) |
| `Extractor` | `src/extractor.py` | pull text + tool calls from LangGraph messages | `langchain_core.messages` |
| `Router` | `src/router.py` | hybrid regex+LLM routing, enrichment passthrough | `ChatOllama`, router prompt |
| `Agents` | `src/agents.py` | LLM+agent lifecycle (Ollama instances, MCP, create_react_agent) | LangGraph, MCP, Ollama, config |
| `Executor` | `src/executor.py` | run agent chain (sequential vision→general) | LangGraph agents |
| `Pipeline` | `src/pipeline.py` | wires all stages; orchestrates the full flow | All of the above |
| `Context` | `src/pipeline.py` | data bag passed between stages | `dataclasses` |

### Data Flow

```
raw_input ──► History.enrich() ──► enriched_input
                 │
raw_input + enriched_input ──► Router.route() ──► agents[]
                 │
raw_input + History.build_messages() ──► messages[]
                 │
agents[] + messages[] ──► Executor.execute() ──► AgentResult(text, tool_calls, vision_context)
                 │
AgentResult.text ──► Extractor.extract() ──► response
AgentResult.tool_calls ──► stored on context
                 │
response ──► Formatter.format() ──► formatted
                 │
formatted ──► History.add_turn() ──► stored for next turn
```

---

## Phase 1: Zero-dependency classes (pure logic, no I/O)

No Ollama, MCP, or DBus needed. Each class has its own test file.

### 1a. `src/history.py` — `History` class

```python
class History:
    def __init__(self, max_turns: int = 10): ...

    def add_turn(self, user_input: str, response: str) -> None: ...
    def build_messages(self, user_input: str, *, include_history: bool = True) -> list[BaseMessage]: ...
    def enrich_for_routing(self, user_input: str) -> str: ...

    @property
    def turns(self) -> int: ...  # current turn count
    def clear(self) -> None: ...
```

Extract from orchestrator: `_build_messages`, `_add_to_history`, `_enrich_for_routing`,
`chat_history` list, `chat_history_size`.

### 1b. `src/formatter.py` — `Formatter` class

```python
class Formatter:
    def __init__(self, enabled: bool = True): ...

    def format(self, text: str) -> str: ...
```

Extract from orchestrator: `_format_response`, `_STRIP_RE`, `_TOOL_CALL_RE`, `_JSON_FENCE_RE`.
Strips emoji, invisible chars, MCP JSON artifacts, markdown code fences.

### 1c. `src/extractor.py` — `Extractor` class

```python
class Extractor:
    @staticmethod
    def response(messages: list) -> str: ...     # final text from LangGraph messages
    @staticmethod
    def tool_calls(messages: list) -> list[dict]: ...  # {name, args, result} per tool
    @staticmethod
    def clean_result(content: str | list) -> str: ...  # normalize MCP tool output
```

Extract from orchestrator: `_last_response`, `_extract_tool_calls`, `_clean_tool_result`.

### Tests

| Test file | Tests |
|---|---|
| `test_history.py` | add/trim/max-size, build_messages with/without history, enrich passthrough + context injection, empty history edge cases |
| `test_formatter.py` | emoji strip, invisible chars, JSON fence removal, MCP artifact removal, disabled mode, no-op on clean text |
| `test_extractor.py` | extract from AIMessage, extract from ToolMessage, extract tool calls, parse list-type result, parse string-type result, skip malformed JSON |

All zero-dependency — run without Ollama.

---

## Phase 2: I/O-dependent classes (need Ollama / LangGraph)

### 2a. `src/router.py` — `Router` class

```python
class Router:
    def __init__(self, llm: ChatOllama, prompt: str = ""): ...

    async def route(self, user_input: str, enriched: str = "") -> list[str]: ...
    async def _llm_is_screen(self, user_input: str) -> bool: ...
```

Extract from orchestrator: `_route`, `_llm_is_screen`, `SCREEN_WORDS`, `ACTION_WORDS`.

### 2b. `src/agents.py` — `Agents` class

```python
class Agents:
    def __init__(self, model: str = None, vision_model: str = None, ...): ...

    async def start(self) -> None: ...   # start MCP subprocess, discover tools, build agents
    async def shutdown(self) -> None: ...  # unload Ollama models

    @property
    def general(self) -> CompiledGraph: ...
    @property
    def vision(self) -> CompiledGraph: ...
    @property
    def general_llm(self) -> ChatOllama: ...  # for Router to reuse
```

Extract from orchestrator: `__init__` (llm creation), `initialize` (MCP + agents),
`close` (VRAM).

### 2c. `src/executor.py` — `Executor` class

```python
class Executor:
    def __init__(self, agents: Agents): ...

    async def execute(self, agents_order: list[str], messages: list, *,
                      vision_context: str = "", user_input: str = "",
                      recursion_limit: int = 10) -> AgentResult: ...
```

Extract from orchestrator: agent loop in `ainvoke` (chaining, context injection,
invocation, tool-call extraction, response extraction).

### Tests

| Test file | Tests |
|---|---|
| `test_router.py` | Unit: regex routing (screen, action, screen+action, none), enriched passthrough. Integration: LLM routing (needs Ollama), no false chain from history words. |
| `test_agents.py` | Integration: MCP startup, tool discovery count, agent creation (tool split vision vs general), shutdown unloads models. |
| `test_executor.py` | Unit: with mocked agents verify chain order, vision→general context injection. Integration: real agents, single-agent execution, chained execution, recursion limit enforcement. |

---

## Phase 3: Pipeline assembly

### 3a. `src/pipeline.py` — `Context` + `Pipeline`

```python
@dataclass
class Context:
    raw_input: str
    enriched_input: str = ""
    agents: list[str] = field(default_factory=list)
    messages: list = field(default_factory=list)
    vision_context: str = ""
    response: str = ""
    formatted: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None

class Pipeline:
    def __init__(self, router: Router, executor: Executor,
                 history: History, formatter: Formatter, extractor: Extractor): ...

    async def process(self, user_input: str) -> str: ...
    # Runs: enrich → route → build → execute → extract → format → store → return

    @property
    def last_tool_calls(self) -> list[dict]: ...
    @property
    def context(self) -> Context: ...  # last run's context for inspection
```

This is the class that `main.py` (and future `api.py`) uses directly.

### Tests

| Test file | Tests |
|---|---|
| `test_pipeline.py` | Unit: with mocked Router+Executor, verify stage ordering, context propagation, error short-circuit. Integration: real pipeline, end-to-end "open firefox", chain test "what do you see and open firefox", history across turns. |

---

## Phase 4: Migration + cleanup

### 4a. Rewrite `src/main.py`

Replace `Orchestrator()` → `Pipeline` built from components:

```python
async def main_async():
    agents = Agents()
    await agents.start()

    pipeline = Pipeline(
        router=Router(llm=agents.general_llm, prompt=read_prompt("router", "")),
        executor=Executor(agents=agents),
        history=History(max_turns=chat_history_size()),
        formatter=Formatter(enabled=formatter_enabled()),
        extractor=Extractor(),
    )

    while True:
        text = input("\nYou: ").strip()
        if text.lower() in ("exit", "quit"):
            break
        response = await pipeline.process(text)
        print(response)
        speak(response)

    await agents.shutdown()
```

### 4b. Rewrite test suite

| Old test | Replaced by |
|---|---|
| `test_phase1.py` | `test_history.py` + `test_formatter.py` + `test_extractor.py` + `test_pipeline.py` |
| `test_phase2.py` | `test_history.py` + `test_router.py` + `test_agents.py` + `test_pipeline.py` |
| `test_phase3.py` | `test_router.py` + `test_executor.py` + `test_pipeline.py` |

### 4c. Delete `src/orchestrator.py`

### 4d. Update debugging

Logger calls move from orchestrator methods to their new class homes:

| Old location | New location |
|---|---|
| `_route` → `.debug("Router (regex): ...")` | `Router.route()` |
| `_route` → `.debug("Route → ...")` | `Router.route()` |
| `_build_messages` → `.info("History: prepending...")` | `History.build_messages()` |
| `_add_to_history` → `.info("History: now ...")` | `History.add_turn()` |
| `ainvoke` chain loop → `.info("Chain step...")` | `Executor.execute()` |
| `ainvoke` chaining → `.info("Chaining: ...")` | `Executor.execute()` |
| `ainvoke` response → `.info("... agent returned ...")` | `Executor.execute()` |
| `_format_response` → `.debug("Formatter: ...")` | `Formatter.format()` |
| `ainvoke` done → `.info("Done: ...")` | `Pipeline.process()` |

---

## File manifest

| Phase | File | Status | Est. lines |
|---|---|---|---|
| 1a | `src/history.py` | New | ~55 |
| 1b | `src/formatter.py` | New | ~40 |
| 1c | `src/extractor.py` | New | ~50 |
| 2a | `src/router.py` | New | ~65 |
| 2b | `src/agents.py` | New | ~80 |
| 2c | `src/executor.py` | New | ~60 |
| 3 | `src/pipeline.py` | New | ~80 |
| 4 | `src/main.py` | Rewrite | ~60 |
| 4 | `src/orchestrator.py` | **Delete** | -360 |
| — | `test_history.py` | New | ~50 |
| — | `test_formatter.py` | New | ~40 |
| — | `test_extractor.py` | New | ~45 |
| — | `test_router.py` | New | ~55 |
| — | `test_agents.py` | New | ~40 |
| — | `test_executor.py` | New | ~50 |
| — | `test_pipeline.py` | New | ~60 |
| — | `test_phase*.py` | **Delete** | ~260 |
| **Total** | | +490 new, -620 old = **-130 net** |

---

## Acceptance criteria per phase

Each phase is independently mergeable (Phases 1-3 don't delete orchestrator.py,
they live alongside it).

### Phase 1
- `History`, `Formatter`, `Extractor` all have passing test suites
- Zero Ollama/MCP dependency — tests run in <1 second
- Orchestrator unchanged, `main.py` unchanged

### Phase 2
- `Router`, `Agents`, `Executor` all have passing test suites
- `Agents.start()` creates working LangGraph agents verified by integration test
- `Executor.execute()` handles single-agent and chained-agent paths
- Orchestrator unchanged, `main.py` unchanged

### Phase 3
- `Pipeline.process("open firefox")` returns correct response, tool calls captured
- `Pipeline.process("what do you see and open firefox")` triggers chain, both tools fire
- History persists across `pipeline.process()` calls
- Three-turn conversation test passes (open → close → "what was that?")
- Orchestrator unchanged (can compare Pipeline output vs Orchestrator output side-by-side)

### Phase 4
- `main.py` uses Pipeline directly, voice loop works
- All old test files removed, new suite passes
- `src/orchestrator.py` deleted
- Debug logging works identically (same `[ROUTER]`, `[LLM →]`, `[TOOL ←]` format)

---

## Rollback

Any phase can be reverted without affecting others:

- Phases 1-3 add new files only — no existing files deleted or modified
- Phase 4 deletes `orchestrator.py` and rewrites `main.py` — git revert restores both
- Independent test files mean a failing Phase 3 doesn't break Phase 1 tests
