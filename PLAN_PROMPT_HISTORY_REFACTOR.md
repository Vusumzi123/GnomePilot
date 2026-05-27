# Plan: Prompt & History Refactor — Decouple, Simplify, Timeout

## Goal

Stop history pollution from corrupting routing decisions, clean up how history is passed to executor agents, add token-aware trimming, simplify the general prompt to reduce LLM confusion, and add timeouts to all LLM calls so the pipeline never hangs.

---

## Current State Analysis

### 1. Enrich for Routing

In `src/pipeline.py:94`:
```python
ctx.enriched_input = self.history.enrich_for_routing(user_input)
```

The `History.enrich_for_routing()` method (history.py:62-74) prepends the last 3 user queries into a single string:
```
[History: hello | can you see my screen?] User: that is your source code
```

This is passed to `Router.route()` as `enriched`, which uses it for the LLM fallback when regex fast-path doesn't match. The router's `_llm_is_screen` sees the user's LAST query ("can you see my screen") in the history prefix and can answer "yes" even though the CURRENT query ("that is your source code") is not about the screen at all.

**Bug:** Router LLM answer is biased by history context. The binary "is this about the screen?" check should only evaluate the CURRENT user input.

**Detail:** The regex fast-path runs on the original input (correct — no contamination). But the LLM fallback line 58-59:
```python
llm_input = enriched or user_input
answer = await self._llm_is_screen(llm_input)
```
passes the enriched + current input as a fused string. The router prompt is:
```
Is the user asking about their computer screen, display, or what they can see?

Answer ONLY "yes" or "no".

Request: [History: hello | can you see my screen?] User: that is your source code
```

The LLM sees "can you see my screen" and returns "yes" — routing to `["vision"]` incorrectly.

### 2. Build Messages Preamble

In `src/history.py:51-58`:
```python
messages.append(HumanMessage(content=(
    "Below is our previous conversation — context only. "
    "Do NOT repeat or re-execute any tool calls shown below. "
    "Reply to my most recent message only."
)))
for turn in self._turns[-self.max_turns:]:
    messages.append(HumanMessage(content=turn["user"]))
    messages.append(AIMessage(content=turn["assistant"]))
```

The preamble is injected as a `HumanMessage`. LLMs treat all HumanMessages as user input — the preamble is indistinguishable from actual user turns. This creates two problems:

1. The instruction "Do NOT repeat or re-execute" becomes just another user message, not a system instruction. LLMs may weigh it lower than the actual behavior rules in the system prompt.
2. The preamble takes up ~200 chars of context and message count, pushing older turns out.

**LangChain `create_react_agent` handles history correctly already** — the system prompt is the first entry in the state, and the LLM knows to treat earlier messages as context. The manually constructed preamble fights this built-in behavior.

### 3. No Token-Aware Trimming

`History.__init__(max_turns=10)` counts turns (user+assistant = 1 turn). But token consumption varies wildly:

| Message type | Typical size | Approx tokens |
|-------------|-------------|---------------|
| "open firefox" | 12 chars | ~3 tokens |
| Vision analysis | 800 chars | ~200 tokens |
| General response | 300 chars | ~75 tokens |
| Router enrichment | 250 chars | ~62 tokens |

A history of 10 vision exchanges = 2000+ tokens of context. For llama3.1:8b (8K context), that's 25% of the budget consumed by stale history. For unified_model: qwen3.5:2b (32K), it's less critical but still wasteful.

The LLM doesn't distinguish "recent and important" from "old and stale" — it weights all history equally unless it's very old (decaying attention).

### 4. General Prompt Too Long

**Current (1479 chars, 9 rules):**

```
line 1:  "You are a helpful AI assistant running on CachyOS (Arch Linux with GNOME)."
line 3-5: "## Tools Available / You have tools to: / {tool_descriptions}"
line 7: "## Behavior"
line 8:  "Use the appropriate tool when the user asks you to perform an action"
line 9:  "Tools will be called automatically — do not write tool calls as text"
line 10: "Keep responses concise and natural"
line 11: "responses should be fun and natural not robotic"
line 12: "NEVER use special characters or emojis in your responses"
line 13: "After a tool returns a result, summarize what happened briefly"
line 14: "If you receive 'Context from vision analysis', use that information to complete the user's request"
line 15: "IMPORTANT: Call each tool ONCE only..."
line 16: "When close_application returns a list of open windows..."
line 17: "You have a web search tool..."
```

**Issues by line:**

| Line | Problem | Action |
|------|---------|--------|
| 10 vs 11-12 | "concise and natural" vs "fun and natural not robotic" vs "NEVER use emojis" — contradictory. "Fun" implies expressiveness; "no emojis" restrains it. | Merge into one clear rule |
| 11 | "fun and natural not robotic" — vague, unenforceable by a small model | Remove |
| 13 | "After a tool returns, summarize what happened briefly" — this is obvious LLM behavior. Redundant instruction. | Remove |
| 14 | "If you receive 'Context from vision analysis'..." — this is a magic-string contract between executor and prompt. It should be a constant in executor.py, not a prompt rule. | Extract to constant, simplify prompt |
| 17 | "You have a web search tool. Use to get data..." — redundant with {tool_descriptions} dynamic injection. | Remove |

Small models (2B-8B) perform worse with longer prompts — they have limited attention and instruction-following capability. A 1479-char prompt with 9 rules causes the LLM to either ignore some rules or apply them inconsistently.

### 5. No Timeout on LLM Calls

All `llm.ainvoke()` calls lack `asyncio.wait_for`:

| Location | Call | Risk |
|----------|------|------|
| `src/router.py:73` | `self.llm.ainvoke([...])` | Router hangs indefinitely on a slow model |
| `src/executor.py:66` | `agent.ainvoke({"messages": ...})` | Full pipeline hangs on the agent execution step |

When the model is overloaded, starting up, or generating a long response, these calls can take 60+ seconds or hang indefinitely. The user sees no feedback and no timeout recovery.

**Observed behavior:** The 20:55:38 hang in the log was a Router LLM call that never returned. The pipeline was stuck on line 97-98 of pipeline.py:
```python
ctx.agents = await self.router.route(user_input, ctx.enriched_input)
#                                                     ^— enriched had 249 chars of history
```

---

## Phase 1: Decouple History from Routing

### What changes

**`src/pipeline.py`** — line 94 becomes a no-op (remove enrichment step), line 97 passes only raw input:

```python
# OLD:
ctx.enriched_input = self.history.enrich_for_routing(user_input)
ctx.agents = await self.router.route(user_input, ctx.enriched_input)

# NEW:
ctx.agents = await self.router.route(user_input)
```

**`src/router.py`** — simplify `route()` signature and internals:

```python
# OLD:
async def route(self, user_input: str, enriched: str = "") -> list[str]:
    ...
    llm_input = enriched or user_input

# NEW:
async def route(self, user_input: str) -> list[str]:
    ...
    # llm_input is always user_input — no history contamination
```

The regex fast-path is unchanged (already operates on raw `user_input`).

The LLM fallback now receives:
```
Is the user asking about their computer screen, display, or what they can see?

Answer ONLY "yes" or "no".

Request: that is your source code
```

Not:
```
Is the user asking about their computer screen, display, or what they can see?

Answer ONLY "yes" or "no".

Request: [History: hello | can you see my screen?] User: that is your source code
```

**`src/history.py`** — `enrich_for_routing()` can remain (backward compat for any external callers) but is no longer called by pipeline. Add deprecation note to its docstring.

**`src/pipeline.py Context`** — `enriched_input` field becomes unused. Remove it to keep the dataclass clean.

### Files modified

| File | Change | Risk |
|------|--------|------|
| `src/pipeline.py` | Remove enrichment step; pass raw user_input to route(); remove `enriched_input` from Context | LOW — `enriched_input` only existed for routing |
| `src/router.py` | Simplify `route()` — remove `enriched` parameter; LLM fallback always uses `user_input` | LOW — existing callers only pass `enriched` |
| `src/history.py` | Deprecate `enrich_for_routing()` in docstring | LOW — no logic change |

### Impact on ambiguous references

The reason `enrich_for_routing` was added: to handle "describe it again" after a vision turn. With the enrichment removed:

- If user says "describe it again" after a vision analysis, the router sees no screen/action keywords → regex no match → LLM fallback evaluates "describe it again" → LLM says "no" (not about screen) → routes to `["general"]`.
- The general agent gets the full history (typed messages), which includes the prior vision turn. The general prompt says "History is context only — reply to the most recent message." The LLM sees:
  ```
  [System prompt: ...]
  Human: look at my screen
  AI: I see Firefox with a terminal window...
  Human: describe it again
  ```
  The LLM naturally resumes describing, because that's what a conversational LLM does with history.

**This works correctly without enrich_for_routing.** The LLM natively handles follow-up questions through typed message history. The enrich mechanism was an unnecessary workaround.

### Manual testing

```bash
# 1. Verify routing without enrichment
source .venv/bin/activate
python3 -c "
from src.router import Router
from langchain_ollama import ChatOllama
import asyncio

async def test():
    llm = ChatOllama(model='llama3.1:8b', temperature=0)
    router = Router(llm, 'Is the user asking about their computer screen? Answer only yes or no.')
    
    # No screen keywords → should route to general (not vision)
    result = await router.route('hello')
    print(f'\"hello\" → {result}')  # Expected: ['general']
    
    result = await router.route('what do you think?')
    print(f'\"what do you think?\" → {result}')  # Expected: ['general']
    
    # Screen keywords → should route to vision
    result = await router.route('look at my screen')
    print(f'\"look at my screen\" → {result}')  # Expected: ['vision']
    
    # Both → chain
    result = await router.route('look at my screen and open firefox')
    print(f'\"look at my screen and open firefox\" → {result}')  # Expected: ['vision', 'general']

asyncio.run(test())
"
```

---

## Phase 2: Clean up History Message Passing to Executor

### What changes

**`src/history.py` `build_messages()`** — remove the preamble HumanMessage:

```python
# OLD:
def build_messages(self, user_input, *, include_history=True):
    messages: list = []
    if include_history and self._turns and self.max_turns > 0:
        messages.append(HumanMessage(content=(
            "Below is our previous conversation — context only. "
            "Do NOT repeat or re-execute any tool calls shown below. "
            "Reply to my most recent message only."
        )))
        for turn in self._turns[-self.max_turns:]:
            messages.append(HumanMessage(content=turn["user"]))
            messages.append(AIMessage(content=turn["assistant"]))
    messages.append(HumanMessage(content=user_input))
    return messages

# NEW:
def build_messages(self, user_input, *, include_history=True):
    messages: list = []
    if include_history and self._turns and self.max_turns > 0:
        for turn in self._turns[-self.max_turns:]:
            messages.append(HumanMessage(content=turn["user"]))
            messages.append(AIMessage(content=turn["assistant"]))
    messages.append(HumanMessage(content=user_input))
    return messages
```

**Why this is safe:** The `create_react_agent` in LangGraph sets the system prompt as the state's initial system message. Typed HumanMessage/AIMessage pairs are naturally interpreted as conversation history by the LLM — no preamble needed. The LLM already knows later messages are the current conversation because:
1. Message ordering — the system prompt is first, then history pairs, then the most recent HumanMessage
2. The LLM's causal attention naturally weighs the most recent message highest
3. No instruction preamble is needed to say "this is history" — typed messages ARE the standard way to represent history

**`prompts/general.md`** — add a single concise history rule to the Behavior section:

```markdown
- History is context only — do not repeat prior tool calls
```

This replaces the 200-char preamble with a ~55-char rule. It lives in the system prompt where it belongs — not injected as a user message.

### Files modified

| File | Change | Risk |
|------|--------|------|
| `src/history.py` | Remove preamble from `build_messages()` | MEDIUM — preamble existed to prevent tool re-execution; verify the prompt rule covers this |
| `prompts/general.md` | Add "History is context only" rule | LOW — reinforces existing langgraph behavior |

### Why no tool re-execution risk

The executor already handles tool re-execution prevention:
1. **Tool dedup detection** in `executor.py:78-88` — detects duplicate (name, args) pairs and prepends a stop warning to the response
2. **The `create_react_agent`** automatically tracks which tool calls have been made in the agent state — it won't re-execute calls from history

The preamble was a band-aid, not a substantive fix. Removing it and adding the prompt rule is safer because:
- The prompt rule is seen as a system instruction (highest priority for the LLM)
- The tool dedup detection is a code-level guard (always runs, can't be ignored by the LLM)
- The agent state tracks tool execution natively

### Manual testing

```bash
# Verify history still works for follow-up queries
source .venv/bin/activate
python3 -c "
import asyncio
from src.history import History

async def test():
    h = History(max_turns=5)
    h.add_turn('open firefox', 'Firefox is now open.')
    h.add_turn('what time is it', 'It is 3:30 PM.')
    
    msgs = h.build_messages('close it', include_history=True)
    print(f'Message count: {len(msgs)}')  # Expected: 5 (4 history + 1 current)
    print(f'No preamble: {msgs[0].content[:30]}')
    # Expected: first message is 'open firefox' (not 'Below is our...')
    print(f'Last message: {msgs[-1].content}')  # Expected: 'close it'

asyncio.run(test())
"
```

---

## Phase 3: Token-Aware History Trimming

### What changes

**`src/history.py`** — add token budget tracking alongside max_turns:

```python
class History:
    def __init__(self, max_turns: int = 10, max_tokens: int = 2000):
        self._turns: list[dict[str, str]] = []
        self.max_turns = max_turns
        self.max_tokens = max_tokens

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Approximate token count: ~4 chars per token for English text."""
        return max(1, len(text) // 4)

    def _trim_to_budget(self):
        """Remove oldest turns until within token budget."""
        while len(self._turns) > 0:
            total = sum(
                self._estimate_tokens(t["user"]) + self._estimate_tokens(t["assistant"])
                for t in self._turns
            )
            if total <= self.max_tokens and len(self._turns) <= self.max_turns:
                break
            self._turns.pop(0)
```

**`build_messages()`** — uses `_trim_to_budget()` before building, or trims during iteration:

```python
def build_messages(self, user_input, *, include_history=True):
    messages: list = []
    if include_history and self._turns and self.max_turns > 0:
        self._trim_to_budget()  # <-- trim before building
        for turn in self._turns:
            messages.append(HumanMessage(content=turn["user"]))
            messages.append(AIMessage(content=turn["assistant"]))
    messages.append(HumanMessage(content=user_input))
    return messages
```

**Alternative approach: trim in `add_turn()` instead** — this avoids trimming on every `build_messages()` call:

```python
def add_turn(self, user_input: str, response: str) -> None:
    if self.max_turns <= 0:
        return
    self._turns.append({"user": user_input, "assistant": response})
    self._trim_to_budget()
```

This is simpler — trimming happens once per turn addition, not once per message build.

### Why char/4 token estimation

Simple division by 4 is:
- Accurate enough (±20%) for English text — OpenAI's own tokenizer averages ~4 chars/token
- Fast — no dependency on tiktoken or tokenizers library
- Deterministic — no model-specific tokenizer needed

If exact token counting is needed later, add `tiktoken` as a dependency and use `encoding = tiktoken.get_encoding("cl100k_base")`.

### What max_tokens value

| Model | Context window | Recommended max_tokens for history |
|-------|---------------|-----------------------------------|
| llama3.1:8b | 8,192 | 2,000 (25% of context) |
| qwen3.5:2b | 32,768 | 4,000 (12% of context) |
| qwen3.5:9b | 32,768 | 4,000 |
| unified (any) | varies | 2,000 (conservative) |

Default: 2000. Configurable via `config.json`:

```json
{
    "orchestrator": {
        "chat_history_size": 10,
        "history_max_tokens": 2000
    }
}
```

`chat_history_size` (already existed) becomes `history_max_turns()` in code. `history_max_tokens` is new. Both have sensible defaults; both are optional in `config.json`.

### File changes

**`src/config.py`** — add config accessors:

```python
def history_max_turns() -> int:
    """Chat history turn ceiling from config (key 'chat_history_size'). Default 10."""
    return int(load_config().get("orchestrator", {}).get("chat_history_size", 10))

def history_max_tokens() -> int:
    """Token budget for history from config (key 'history_max_tokens'). Default 2000."""
    return int(load_config().get("orchestrator", {}).get("history_max_tokens", 2000))
```

**`src/history.py`** — add `_estimate_tokens()`, `_trim_to_budget()`, update `add_turn()`, update `build_messages()`.

**`src/pipeline.py`** — pass both `history_max_tokens` and `history_max_turns` to History constructor:

```python
# OLD: self.history = History(max_turns=max_turns)
# NEW:
max_turns = history_max_turns()
max_tokens = history_max_tokens()
self.history = History(max_turns=max_turns, max_tokens=max_tokens)
```

### Manual testing

```bash
source .venv/bin/activate
python3 -c "
import asyncio
from src.history import History

h = History(max_turns=10, max_tokens=200)
h.add_turn('hello', 'Hi!' * 80)    # ~240 chars → ~60 tokens each = ~120 total
h.add_turn('how are you', 'Good!' * 80)  # ~240 chars → ~120 tokens → total exceeds 200
print(f'Turns after budget trim: {h.turns}')  # Expected: 1 (oldest trimmed)
# Verify: first turn was 'hello', should be gone
print(f'Remaining user: {h._turns[0][\"user\"]}')  # Expected: 'how are you'
"
```

### Edge cases

| Case | Behavior |
|------|----------|
| Single turn exceeds max_tokens | Kept (must have at least 1 turn in history) |
| max_tokens <= 0 | All history cleared (equivalent to include_history=False or max_turns=0) |
| Both max_turns and max_tokens limits hit | Whichever is stricter wins |
| Empty history | _trim_to_budget is no-op |
| After trim, only 1 turn left | Correct — enough for "describe it again" follow-ups |

---

## Phase 4: Simplify General Prompt

### Current vs Target

**Current** (1479 chars, 9 rules):
```
You are a helpful AI assistant running on CachyOS (Arch Linux with GNOME).

## Tools Available
You have tools to:
{tool_descriptions}

## Behavior
- Use the appropriate tool when the user asks you to perform an action
- Tools will be called automatically — do not write tool calls as text
- Keep responses concise and natural
- responses should be fun and natural not robotic
- NEVER use special characters or emojis in your responses
- After a tool returns a result, summarize what happened briefly
- If you receive 'Context from vision analysis', use that information to complete the user's request
- IMPORTANT: Call each tool ONCE only. Do not retry or repeat the same tool call. When the tool returns a result, trust it and respond to the user. Never call a tool more than once for the same thing. If the tool reports failure, tell the user — do not try other tools to work around it.
- When close_application returns a list of open windows ("Currently open windows:"), help the user identify which window to close. Do NOT call close_application again unless the user gives a specific name from the list.
- You have a web search tool. Use to get data (current events, specific facts). Limit to 1–2 searches per conversation. Never search for opinions, advice, or things you can answer yourself.
```

**Target** (~580 chars, 5 rules):
```
You are a helpful AI assistant running on CachyOS (Arch Linux with GNOME).

## Tools Available
You have tools to:
{tool_descriptions}

## Behavior
- Use tools automatically when asked — do not write them as text
- Keep responses concise. Plain text only — no special characters.
- History is context only — do not repeat prior tool calls. Reply to the most recent message.
- Call each tool ONCE. Trust the result — never retry. If it fails, tell the user.
- When close_application lists open windows, help identify which to close. Do not call it again unless the user gives a specific name from the list.
```

### What was removed and why

| Removed text | Reason | Mitigation |
|-------------|--------|------------|
| `responses should be fun and natural not robotic` | Vague and contradictory with "no emojis". Small models can't reliably interpret "fun but not robotic". | Merged into "Keep responses concise" — conciseness is a clear, measurable instruction |
| `NEVER use special characters or emojis in your responses` | Redundant — merged into "Plain text only — no special characters" | Single clear rule |
| `After a tool returns a result, summarize what happened briefly` | Obvious LLM behavior — all instruction-tuned models summarize tool results naturally | Not needed |
| `If you receive 'Context from vision analysis', use that information to complete the user's request` | Magic string; this is an executor implementation detail, not a user-facing behavior rule | Moved to `VISION_CONTEXT_PREFIX` constant in executor.py. The executor constructs the prompt; the model doesn't need to know about the string naming |
| `You have a web search tool. Use to get data... Never search for opinions...` | Redundant — {tool_descriptions} already describes the tool and its purpose. The "never search for opinions" rule was unenforceable (the LLM decides what to search for) | {tool_descriptions} handles tool awareness |

### What was consolidated

| Old rules | New rule |
|-----------|----------|
| "Use the appropriate tool" + "Tools will be called automatically — do not write tool calls as text" | "Use tools automatically when asked — do not write them as text" |
| "Keep responses concise and natural" + "NEVER use emojis" + "responses should be fun and natural not robotic" | "Keep responses concise. Plain text only — no special characters." |
| "Call each tool ONCE only. Do not retry..." + (future: "do not repeat prior tool calls") | "Call each tool ONCE. Trust the result — never retry. If it fails, tell the user." |
| (future: history preamble) + existing close_application rule | "History is context only — do not repeat prior tool calls. Reply to the most recent message." |

### Why this works for both chat and tool-use

The simplified prompt doesn't distinguish between chat and tool-use queries — it simply says:
1. Use tools when appropriate (tool-use queries)
2. Keep responses concise (chat queries)
3. Don't repeat history (both)
4. Call each tool once (tool-use guard)
5. Close_application window list (tool-specific edge case)

A "hello" query triggers no tools → rule 1 is a no-op, rules 2-3 apply → LLM says "Hello! How can I help?" (concise, no tool use).

A "open firefox" query triggers tool → rule 1 fires, rule 4 prevents retry → LLM calls open_application once and reports the result concisely.

### File changes

| File | Change | Risk |
|------|--------|------|
| `prompts/general.md` | Complete rewrite of Behavior section | MEDIUM — verify the simplified prompt doesn't miss edge cases |
| `src/executor.py` | Add `VISION_CONTEXT_PREFIX` constant | LOW — extracts existing string; no behavior change |

### Manual testing

```bash
# 1. Verify prompt length
source .venv/bin/activate
wc -c prompts/general.md
# Expected: ~600 chars

# 2. Run integration tests
python3 run_tests.py --integration
# Expected: 4/4 pass (test_agents, test_executor, test_pipeline, test_close)

# 3. Manual smoke test — chat
python3 -m src.main
# Type: "hello"
# Expected: concise reply, no tool calls

# 4. Manual smoke test — tool use
# Type: "open firefox"
# Expected: Firefox opens, one tool call, concise summary
```

---

## Phase 5: Add LLM Call Timeouts

### What changes

**`src/router.py` `_llm_is_screen()`** — wrap ainvoke with 15-second timeout:

```python
import asyncio

async def _llm_is_screen(self, user_input: str) -> bool:
    if not self.prompt:
        return False
    try:
        msg = await asyncio.wait_for(
            self.llm.ainvoke([
                HumanMessage(content=f"{self.prompt}\n\nRequest: {user_input}")
            ]),
            timeout=self._timeout,
        )
        content = msg.content
        if isinstance(content, list):
            content = " ".join(str(c) for c in content)
        return content.strip().lower().startswith("yes")
    except asyncio.TimeoutError:
        logger.warning("Router LLM timeout ({}s) — falling back to general", self._timeout)
        return False
    except Exception:
        return False
```

**`src/executor.py` `execute()`** — wrap agent.ainvoke with configurable timeout:

```python
import asyncio

async def execute(self, agents_order: list[str], messages: list, *,
                  vision_context: str = "", user_input: str = "",
                  recursion_limit: int = 10, timeout: int = 60) -> AgentResult:
    ...
    for i, name in enumerate(agents_order):
        ...
        try:
            result = await asyncio.wait_for(
                agent.ainvoke(
                    {"messages": current_messages},
                    {"recursion_limit": recursion_limit},
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.error("{} agent timed out after {}s", name, timeout)
            response = f"I was unable to complete that request — the {name} agent timed out."
            if name == "vision":
                vision_context = response
            final_text = response
            continue
        ...
```

**`src/config.py`** — add timeout accessors:

```python
DEFAULT_CONFIG = {
    "models": {...},
    "orchestrator": {
        "temperature": 0,
        "chat_history_size": 10,
        "recursion_limit": 10,
    },
    # ... existing keys ...
}

def router_timeout() -> int:
    """Router LLM timeout in seconds."""
    return int(load_config().get("orchestrator", {}).get("router_timeout", 15))

def executor_timeout() -> int:
    """Per-agent execution timeout in seconds."""
    return int(load_config().get("orchestrator", {}).get("executor_timeout", 60))
```

**`src/pipeline.py`** — pass timeout to executor:

```python
result = await self.executor.execute(
    ctx.agents, ctx.messages, user_input=user_input,
    recursion_limit=cfg_recursion_limit(),
    timeout=executor_timeout(),
)
```

### Timeout fallback behavior

| Location | Timeout | Fallback |
|----------|---------|----------|
| Router `_llm_is_screen` | 15s | Return False (route to general) |
| Executor agent.ainvoke | 60s | Return error message, continue to next agent if chain |
| Executor agent.ainvoke (vision only) | 60s | Return "vision agent timed out", general agent proceeds without vision context |

**Why router timeout is shorter (15s):**
- Router only needs a binary yes/no — fast model response expected
- If the model is slow, it's faster to fall back to default routing (general) than to wait
- The regex fast-path handles most cases (screen keyword, action keyword) — the LLM fallback is only for ambiguous queries

**Why executor timeout is longer (60s):**
- Agent execution may involve tool calls (app launch, web search, DBus calls) — these add latency
- The model may generate a long response with multiple tool calls
- 60 seconds is a reasonable upper bound for any single agent invocation

### Configurability

```json
{
    "orchestrator": {
        "router_timeout": 15,
        "executor_timeout": 60
    }
}
```

Both default to sensible values if not present in config.

### File changes

| File | Change | Risk |
|------|--------|------|
| `src/router.py` | Add `asyncio.wait_for` + `TimeoutError` catch in `_llm_is_screen` | LOW — timeout exception is caught; fallback is safe |
| `src/executor.py` | Add `asyncio.wait_for` + `TimeoutError` catch in `execute()` | LOW — fallback message is returned; pipeline continues |
| `src/config.py` | Add `router_timeout()`, `executor_timeout()` accessors | LOW — new functions, no existing code changes |
| `src/pipeline.py` | Pass `executor_timeout()` to executor.execute() | LOW — parameter addition, no behavior change |
| `config.json` | Optional: add `router_timeout` and `executor_timeout` to orchestration section | LOW — optional fields with defaults |

### Manual testing

```bash
# 1. Test router timeout (simulate slow model)
source .venv/bin/activate
python3 -c "
import asyncio
from src.router import Router
from langchain_ollama import ChatOllama

async def test():
    llm = ChatOllama(model='llama3.1:8b', temperature=0, num_predict=1)
    # Use very short timeout to trigger
    router = Router(llm, 'Is the user asking about their screen? Answer only yes or no.')
    router._timeout = 0.001  # force timeout
    
    result = await router._llm_is_screen('hello')
    print(f'Timeout result: {result}')  # Expected: False (fallback)

asyncio.run(test())
"

# 2. Integration test (normal operation)
python3 run_tests.py --integration
# Expected: 4/4 pass (timeouts are high enough not to interfere)

# 3. Manual smoke test — verify fallback on timeout
# (Simulate by setting router_timeout: 1 in config.json temporarily)
python3 -m src.main
# Type: "what do you think about the weather"
# Expected: routes to general (timeout on router → fallback False)
```

---

## Analysis: Should We Add a Conversational Agent?

### The idea

Add a third agent (or route) that handles non-tool queries ("hello", "what do you think?") without any tools. The Router would make a 3-way decision, routing directly to this agent for pure chat.

### Why NOT to do it

**1. The Router already makes a binary decision.** Adding a third route means Router must distinguish "chat" from "general with tools" from "vision". The LLM fallback currently returns `yes` (vision) or `no` (general). A 3-way decision requires a more complex prompt (classify into 3 categories) which is more brittle and error-prone.

**2. The general agent already handles chat natively.** The `create_react_agent` with 0 tools simply responds conversationally — the system prompt says "Use tools automatically when asked", and if no tools match, the LLM responds naturally. There's no performance benefit to a separate agent — the same model, same prompt, same overhead.

**3. It adds routing complexity without solving the core problem.** The issue isn't that the general agent has tools — it's that the prompt was too long and contradictory. Simplifying the prompt (Phase 4) fixes the "LLM over-thinks simple questions" problem directly. Adding a chat agent would be treating the symptom, not the cause.

**4. The "chat vs. tool-use" boundary is fuzzy.** "Search the web for Python 3.14" → tools. "What's your opinion on Python 3.14?" → maybe tools? A routing decision here is inherently ambiguous — the general agent handles this fine by deciding whether to use tools based on the query content.

**5. Follow-up queries need tools.** A chat agent with NO tools can't handle:
```
User: open firefox      → needs tools (would route to general via chat agent's lack of tool... wait, that breaks)
```

The problem is circular — if the user is chatting and then says "open firefox", you need tool access. Splitting these forces the Router to re-evaluate every message, making chat impossible for multi-turn tool tasks.

### When a conversational agent WOULD make sense

If the system were:
- Using a **much smaller, faster model** for chat (e.g., qwen3.5:0.5b) while the general agent uses a larger model
- Processing **stateless requests** where each turn is independent (no follow-up tool use)
- Under very **high traffic** where tool-agent overhead per request matters

None of these apply to this project (single user, single model, conversational mode with follow-ups).

### Recommendation

Skip the conversational agent. Simplify the general prompt (Phase 4) instead — this addresses the root cause (LLM confusion from long prompts) without adding routing complexity.

---

## Full file change summary

| File | Phase | Change |
|------|-------|--------|
| `src/pipeline.py` | 1 | Remove enrichment step; remove `enriched_input` from Context dataclass; pass `user_input` only to route() |
| `src/pipeline.py` | 3 | Pass `history_max_tokens()` and `history_max_turns()` to History constructor |
| `src/pipeline.py` | 5 | Pass `executor_timeout()` to executor.execute() |
| `src/router.py` | 1 | Simplify `route()` — remove `enriched` parameter; LLM fallback always uses `user_input` |
| `src/router.py` | 5 | Add `asyncio.wait_for` in `_llm_is_screen()` with router_timeout; catch TimeoutError → return False |
| `src/history.py` | 1 | Deprecate `enrich_for_routing()` in docstring |
| `src/history.py` | 2 | Remove preamble from `build_messages()` |
| `src/history.py` | 3 | Add `_estimate_tokens()`, `_trim_to_budget()`; update constructor for `max_tokens` and `max_turns`; update `add_turn()` to trim |
| `src/executor.py` | 2 | Add `VISION_CONTEXT_PREFIX` = `"Context from vision analysis (already completed):"` constant |
| `src/executor.py` | 5 | Add `asyncio.wait_for` in `execute()` with per-agent timeout; catch TimeoutError → error message |
| `src/config.py` | 3 | Add `history_max_tokens()`, `history_max_turns()` accessors |
| `src/config.py` | 5 | Add `router_timeout()`, `executor_timeout()` accessors |
| `prompts/general.md` | 2 | Add "History is context only — do not repeat prior tool calls" rule |
| `prompts/general.md` | 4 | Rewrite Behavior section — 5 rules, ~580 chars |
| `config.json` | 3,5 | Add all new keys to `orchestrator` section |

---

## Config.json reference (consolidated)

Every setting lives in `config.json` under `orchestrator`, and optionally in `DEFAULT_CONFIG` within `src/config.py`. All keys are optional — sensible defaults apply when absent.

```json
{
    "orchestrator": {
        "chat_history_size": 10,
        "history_max_tokens": 2000,
        "recursion_limit": 10,
        "router_timeout": 15,
        "executor_timeout": 60
    }
}
```

| Key | Default | Phase | Description |
|-----|---------|-------|-------------|
| `chat_history_size` | 10 | 3 | Hard ceiling on stored conversation turns (already existed, exposed as `history_max_turns` accessor). |
| `history_max_tokens` | 2000 | 3 | Token budget for history — oldest turns trimmed when exceeded. Uses char/4 estimation. |
| `recursion_limit` | 10 | — | LangGraph recursion steps per agent (already existed, unchanged). |
| `router_timeout` | 15 | 5 | `asyncio.wait_for` timeout for Router `_llm_is_screen`. On timeout → fallback to `["general"]`. |
| `executor_timeout` | 60 | 5 | `asyncio.wait_for` timeout per `agent.ainvoke`. On timeout → error message; chain continues if applicable. |

### Accessor mapping in `src/config.py`

```python
def history_max_turns() -> int:
    """Chat history turn ceiling from config (key 'chat_history_size'). Default 10."""
    return int(load_config().get("orchestrator", {}).get("chat_history_size", 10))

def history_max_tokens() -> int:
    """Token budget for history from config (key 'history_max_tokens'). Default 2000."""
    return int(load_config().get("orchestrator", {}).get("history_max_tokens", 2000))

def router_timeout() -> int:
    """Router LLM call timeout in seconds (key 'router_timeout'). Default 15."""
    return int(load_config().get("orchestrator", {}).get("router_timeout", 15))

def executor_timeout() -> int:
    """Per-agent execution timeout in seconds (key 'executor_timeout'). Default 60."""
    return int(load_config().get("orchestrator", {}).get("executor_timeout", 60))
```

## Not changed

| Aspect | Why not |
|--------|---------|
| `History.enrich_for_routing()` | Kept for backward compat (not removed, just deprecated). Any external code that uses it continues to work. |
| `.env` or environment variables | Timeouts are config-level, not env-level. If env vars are needed later, `src/config.py` can be updated to check both. |
| Tests | All existing tests should pass unchanged — the changes are structural, not behavioral. Add new tests only for new functionality (token trimming, timeouts). |
| `prompts/vision.md` | Already simplified in a prior cycle. No issues with vision prompts. |
| `prompts/router.md` | Currently 3 lines — fine as-is. |
| Agent structure in `agents.py` | No changes to agent creation, tool lists, or model selection. |

## Verification checklist

- [ ] Phase 1: Router LLM fallback receives only `user_input`, no history prefix
- [ ] Phase 1: `Context.enriched_input` removed from pipeline dataclass
- [ ] Phase 2: `build_messages()` returns clean typed message pairs without preamble
- [ ] Phase 2: `prompts/general.md` contains "History is context only" rule
- [ ] Phase 3: History trims by token budget in addition to max_turns
- [ ] Phase 3: `_estimate_tokens()` uses char/4 approximation
- [ ] Phase 3: `_trim_to_budget()` keeps at least 1 turn
- [ ] Phase 3: Configurable via `history_max_tokens` and `chat_history_size` in config.json
- [ ] Phase 4: General prompt is ~580 chars with 5 behavior rules
- [ ] Phase 4: `VISION_CONTEXT_PREFIX` extracted as constant in executor.py
- [ ] Phase 5: Router `_llm_is_screen` has 15s timeout → falls back to False
- [ ] Phase 5: Executor `execute()` has 60s timeout per agent → returns error message
- [ ] Phase 5: Timeouts configurable via config.json
- [ ] All 12/12 unit tests pass
- [ ] All 4/4 integration tests pass
- [ ] Manual smoke: "hello" → concise reply, no tools
- [ ] Manual smoke: "look at my screen" → screenshot captured
- [ ] Manual smoke: "describe it again" (after vision) → uses history naturally
- [ ] Manual smoke: "look at my screen and open firefox" → chain works
- [ ] Manual smoke: slow model → timeout fallback, not hang

## Rollback plan

If any phase causes regressions, revert by phase:

```bash
# Phase 1: Restore enrichment in pipeline
git checkout src/pipeline.py src/router.py src/history.py

# Phase 2: Restore preamble logic
git checkout src/history.py prompts/general.md

# Phase 3: Restore simple turn-count trimming
git checkout src/history.py src/config.py src/pipeline.py

# Phase 4: Restore old prompt
git checkout prompts/general.md

# Phase 5: Restore no-timeout calls
git checkout src/router.py src/executor.py src/config.py src/pipeline.py
```

The phases are independent enough that rolling back one doesn't affect the others. Phase 1-5 can be applied in any order, though Phase 1 + 2 are synergistic (both clean up history contamination).
