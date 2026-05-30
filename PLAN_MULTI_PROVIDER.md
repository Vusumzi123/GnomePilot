# Multi-Provider Model Support Plan

## Goal

Allow GnomePilot to use LLMs from multiple providers. Each role (orchestrator, vision, router) gets its own configurable provider and model.

**Supported providers (by phase):**

| Phase | Providers | LangChain class | Config key |
|-------|-----------|-----------------|------------|
| 1 | Ollama, OpenAI | `ChatOllama`, `ChatOpenAI` | `"ollama"`, `"openai"` |
| 2 | DeepSeek, Qwen, OpenRouter | `ChatOpenAI` (custom `base_url`) | `"deepseek"`, `"qwen"`, `"openrouter"` |
| Future | Google, Anthropic | `ChatGoogleGenerativeAI`, `ChatAnthropic` | `"google"`, `"anthropic"` |

All OpenAI-compatible providers (OpenAI, DeepSeek, Qwen, OpenRouter) share `ChatOpenAI` — only `base_url` differs.

---

## Decisions

| Decision | Choice |
|----------|--------|
| Config granularity | Per-role (orchestrator, vision, router each have independent provider+model) |
| API key storage | `config.json` (secrets live locally in the untracked config file) |
| `config.json` lifecycle | Stop git-tracking, add to `.gitignore`, auto-generate defaults on first run |
| Dependencies | All provider packages in `requirements.txt` (no extras) |
| Factory pattern | Single `create_llm()` dispatches by `provider` key; adding a new provider means adding one case + its kwarg filter list |
| Rollback safety | Existing string-only `config.json` continues to work identically (Ollama only) |

---

## Phase 1 — Ollama + OpenAI

### Scope

New config schema, config bootstrap, `model_factory.py`, agents wiring, provider support for Ollama and OpenAI.

### [1a] Stop tracking `config.json` + add `.gitignore`

**Files:** `.gitignore`, `config.json.example`

- `git rm --cached config.json` — stop tracking
- Add `config.json` to `.gitignore`
- Create `config.json.example` at project root (Ollama-only, no secrets, same defaults as today)

**Test:** `git status` shows `config.json` as untracked, `.gitignore` contains the entry.

### [1b] Config bootstrap at startup

**File:** `src/config.py`

- New function `bootstrap_config_if_missing()`:
  - If `config.json` does not exist at startup, write a default one to disk
  - Default content: identical to today's `config.json` (Ollama `llama3.1:8b` + `qwen3.5:2b`, no providers, no API keys)
- Call `bootstrap_config_if_missing()` at the top of `main_async()` in `src/main.py`

**Tests:**
- Unit: Delete config.json, call bootstrap, assert file created with expected default content
- Unit: If config.json exists, bootstrap does nothing
- Integration: App starts without config.json, creates it, runs normally

### [1c] Per-role config schema

**File:** `src/config.py`

- New function `model_config(role: str) -> dict`:
  - Reads `models.{role}` from config (e.g. `models.orchestrator`, `models.vision`, `models.router`)
  - If value is a **string** → normalize to `{"provider": "ollama", "model": "<string>"}`
  - If value is an **object** → use as-is, default `provider` to `"ollama"` if missing
  - If value is missing entirely → return default Ollama config for that role
  - Returns a flat dict ready to pass to `create_llm()`

- New function `unified_model_config() -> dict | None`:
  - Reads `unified_model` key
  - If a **string** → `{"provider": "ollama", "model": "<string>"}`
  - If an **object** → use as-is
  - If `null` or missing → `None` (per-role mode)

- `unified_model()` accessor marked **deprecated** in docstring (kept for backward compat)

**Config examples:**

```jsonc
// String shorthand (Ollama) — backward compatible
{ "models": { "orchestrator": "llama3.1:8b", "vision": "qwen3.5:2b" } }

// Per-role objects — Ollama orchestrator, OpenAI vision, Ollama router
{
  "models": {
    "orchestrator": { "provider": "ollama", "model": "llama3.1:8b", "num_ctx": 32768 },
    "vision": { "provider": "openai", "model": "gpt-4o", "api_key": "sk-..." },
    "router": "llama3.1:8b"
  },
  "unified_model": null
}

// Unified override (all roles use same model)
{ "unified_model": { "provider": "openai", "model": "gpt-4o", "api_key": "sk-..." } }
```

**Tests:**
- `model_config` with string → returns normalized dict
- `model_config` with object → passes through
- `model_config` with missing key → returns default
- `unified_model_config` with string, object, null, missing key

### [1d] `model_factory.py` — LLM instance factory

**New file:** `src/model_factory.py`

- Single public function: `create_llm(config: dict, callbacks: list | None = None) -> BaseChatModel`
- Keyword arguments from `config` are filtered per provider before passing to the constructor
- Design explicitly for easy extension: new provider = new case in dispatch + new kwarg allowlist

**Provider dispatch (Phase 1):**

| `provider` value | LangChain class | Default `base_url` | API key field |
|---|---|---|---|
| `"ollama"` | `ChatOllama` | — | env only (no key in config) |
| `"openai"` | `ChatOpenAI` | `https://api.openai.com/v1` | `api_key` |

**Kwarg filtering per provider:**

| Parameter | ollama | openai |
|-----------|--------|--------|
| `model` | ✓ | ✓ |
| `temperature` | ✓ | ✓ |
| `stop` | ✓ | ✓ |
| `callbacks` | ✓ | ✓ |
| `num_ctx` | ✓ | — |
| `keep_alive` | ✓ | — |
| `base_url` | — | ✓ |
| `api_key` | — | ✓ |
| `max_tokens` | — | ✓ |
| `top_p` | — | ✓ |
| (unknown) | dropped (debug log) | dropped (debug log) |

- If `provider` is unknown → raise `ValueError(f"Unknown provider: {provider}")`
- The kwarg allowlist is a dict literal per provider — adding `"deepseek"` in Phase 2 means adding one entry to the dispatch table and one allowlist (it will be identical to `"openai"`'s since they share `ChatOpenAI`)

**Tests:**
- `ollama` returns `ChatOllama` with correct model name
- `openai` returns `ChatOpenAI` with correct model name
- Unknown provider raises `ValueError`
- `num_ctx` passed to ollama works, passed to openai is silently dropped
- Callbacks attached correctly
- String config normalized before reaching factory

### [1e] Wire into `Agents` class

**File:** `src/agents.py`

Constructor changes:
- Import `create_llm` from `src.model_factory`
- Import `model_config`, `unified_model_config` from `src.config`
- Replace three hardcoded `ChatOllama(...)` calls with `create_llm()` invocations:

```python
unified = unified_model_config()
if unified is not None:
    llm_cfg = vision_cfg = router_cfg = unified
else:
    llm_cfg = model_config("orchestrator")
    vision_cfg = model_config("vision")
    router_cfg = model_config("router")

# Router gets strict stop tokens
router_cfg = {**router_cfg, "temperature": 0, "stop": ["\n"]}

self._general_llm = create_llm(llm_cfg, **cb_kwargs)
self._vision_llm = create_llm(vision_cfg, **cb_kwargs)
self._router_llm = create_llm(router_cfg, **cb_kwargs)
```

`shutdown()` changes:
- Only call `ollama.generate(...keep_alive=0)` if at least one active role uses Ollama provider
- Check `{llm_cfg, vision_cfg, router_cfg}` for `"ollama"` provider

Constructor signature simplified:
- Remove `model`, `vision_model`, `temperature` parameters (config-driven now)
- Keep backward-compatible `**kwargs` as silent passthrough for any caller still passing these

**Tests:**
- Unit: Agents with string config → `_general_llm` is `ChatOllama`
- Unit: Agents with `"openai"` config → `_general_llm` is `ChatOpenAI`
- Unit: `unified_model` set → all three LLMs use the same config
- Unit: shutdown skips ollama unload when no ollama provider in use
- Integration: Agents start, create agents, shutdown — unchanged behavior with default config

### [1f] `src/main.py` bootstrap call

**File:** `src/main.py`

- Insert `bootstrap_config_if_missing()` as first line of `main_async()`
- Agents constructor call drops explicit `model=`/`temperature=` kwargs (config-driven now)

**Test:** Delete `config.json`, start app → config.json created with defaults, app runs normally.

### [1g] `requirements.txt`

Add:
```
langchain-openai>=0.3.0
```

**Test:** `pip install -r requirements.txt` succeeds, imports work.

### [1h] Tests

**New file:** `tests/test_model_factory.py`

| Test | Type | Description |
|------|------|-------------|
| `ollama returns ChatOllama` | Unit | Valid ollama config → instance of ChatOllama |
| `openai returns ChatOpenAI` | Unit | Valid openai config → instance of ChatOpenAI |
| `unknown provider raises` | Unit | `{"provider": "nonexistent"}` → ValueError |
| `ollama num_ctx passed through` | Unit | `num_ctx=4096` appears in ChatOllama kwargs |
| `openai num_ctx silently dropped` | Unit | `num_ctx` in openai config → no error, debug log |
| `callbacks attached` | Unit | Callbacks list reaches constructor |
| `ollama kwargs filtered` | Unit | Unknown kwarg silently dropped for ollama |
| `openai kwargs filtered` | Unit | Unknown kwarg silently dropped for openai |

**Updated file:** `tests/test_config.py`

| Test | Type | Description |
|------|------|-------------|
| `model_config string` | Unit | String value → normalized to `{provider: "ollama", model: ...}` |
| `model_config object` | Unit | Object value → passed through, default provider = ollama |
| `model_config missing` | Unit | Missing key → returns default Ollama config |
| `unified_model_config string` | Unit | String → normalized |
| `unified_model_config object` | Unit | Object → passed through |
| `unified_model_config null` | Unit | null → None |
| `bootstrap creates if missing` | Unit | No config.json → file created with defaults |
| `bootstrap skips if exists` | Unit | Existing config.json → no change |
| `bootstrap default content` | Unit | Generated file matches expected defaults |

**Updated file:** `tests/test_agents.py`

| Test | Type | Description |
|------|------|-------------|
| `string config -> ChatOllama` | Unit | Default config → general_llm is ChatOllama |
| `openai config -> ChatOpenAI` | Unit | OpenAI config → general_llm is ChatOpenAI |
| `unified overrides all roles` | Unit | unified_model set → same config for all 3 LLMs |
| `shutdown skips ollama when not in use` | Unit | No ollama provider → no ollama.ps() call |

---

## Phase 2 — DeepSeek, Qwen, OpenRouter

### Scope
Add 3 OpenAI-compatible providers. Each uses `ChatOpenAI` with a different `base_url`. No new dependencies.

### [2a] Update `model_factory.py` dispatch

Add to the dispatch table:

| `provider` value | LangChain class | Default `base_url` | API key field |
|---|---|---|---|
| `"deepseek"` | `ChatOpenAI` | `https://api.deepseek.com` | `api_key` |
| `"qwen"` | `ChatOpenAI` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `api_key` |
| `"openrouter"` | `ChatOpenAI` | `https://openrouter.ai/api/v1` | `api_key` |

Each reuses the `"openai"` kwarg allowlist (same class, same params).

### [2b] Update `config.json.example`

Add comments/placeholders for DeepSeek, Qwen, OpenRouter:

```jsonc
{ "provider": "deepseek", "model": "deepseek-chat", "api_key": "your-key", "base_url": "https://api.deepseek.com" }
```

### [2c] Tests

| Test | Type | Description |
|------|------|-------------|
| `deepseek returns ChatOpenAI` | Unit | DeepSeek config → ChatOpenAI with `base_url="https://api.deepseek.com"` |
| `qwen returns ChatOpenAI` | Unit | Qwen config → ChatOpenAI with dashscope base_url |
| `openrouter returns ChatOpenAI` | Unit | OpenRouter config → ChatOpenAI with openrouter.ai base_url |
| `all three accept openai kwargs` | Unit | `max_tokens`, `top_p`, `api_key` all pass through |

No changes to `test_config.py` or `test_agents.py` — config schema is unchanged (just new `provider` values), agents code is unchanged (the factory handles dispatch).

---

## Phase 3 — Future: Google + Anthropic

### Scope *(not yet scheduled, architecture prepared)*

Add `"google"` and `"anthropic"` provider support. Requires new dependencies.

### Changes
- Add `langchain-google-genai` and `langchain-anthropic` to `requirements.txt`
- Add two cases to `model_factory.py` dispatch table
- Add two kwarg allowlists

| Provider | Class | API key field |
|----------|-------|---------------|
| `"google"` | `ChatGoogleGenerativeAI` | `api_key` (or `GOOGLE_API_KEY` env) |
| `"anthropic"` | `ChatAnthropic` | `api_key` (or `ANTHROPIC_API_KEY` env) |

**Kwarg filtering:**

| Parameter | ollama | openai-compat | google | anthropic |
|-----------|--------|---------------|--------|-----------|
| `model` | ✓ | ✓ | ✓ | ✓ |
| `temperature` | ✓ | ✓ | ✓ | ✓ |
| `stop` | ✓ | ✓ | — | ✓ |
| `callbacks` | ✓ | ✓ | ✓ | ✓ |
| `num_ctx` | ✓ | — | — | — |
| `keep_alive` | ✓ | — | — | — |
| `base_url` | — | ✓ | — | — |
| `api_key` | — | ✓ | ✓ | ✓ |
| `max_tokens` | — | ✓ | ✓ | ✓ |
| `top_p` | — | ✓ | — | ✓ |
| `top_k` | — | — | ✓ | — |

Unknown kwargs silently dropped (debug log).

---

## What is explicitly out of scope

| Component | Reason |
|-----------|--------|
| `Router.route()` | Uses `self.llm.ainvoke()` — `BaseChatModel` standard method, no change needed |
| `Executor.execute()` | Calls `agent.ainvoke()` on LangGraph agents — provider-agnostic |
| `Pipeline.process()` | No model visibility |
| `History.*` | Unrelated |
| `Formatter.*` | Unrelated |
| MCP tools (`src/tools/*`) | Unrelated |
| Prompts (`prompts/*`) | Unrelated |
| Voice (`src/voice.py`) | Unrelated |

---

## Rollback strategy

Every config change is backward compatible:
- String model values → treated as Ollama (same as today)
- `unified_model` string or null → works as before
- Old `Agents(model=..., vision_model=...)` kwargs → silently accepted via `**kwargs`
- Old `config.json` without `models.router` → router falls back to same model as orchestrator

To roll back entirely: `git checkout config.json` (restore tracked version), revert source files.
