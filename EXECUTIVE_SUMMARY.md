# Executive Summary — 2026-05-28 (Multi-Provider Phase 1)

## Changes Executed

### Phase 1: Ollama + OpenAI Multi-Provider Support (PLAN_MULTI_PROVIDER.md)

Implemented the full Phase 1 of the multi-provider architecture — GnomePilot now supports Ollama AND OpenAI LLMs, with per-role provider configuration, automatic config bootstrap, and a clean factory pattern for extending to additional providers.

---

### 1a: Stop tracking config.json + add .gitignore

| File | Change |
|------|--------|
| `config.json` | `git rm --cached` — no longer tracked in git |
| `.gitignore` | Added `config.json` entry |
| `config.json.example` | **New** — committed template with Ollama defaults, no secrets |

**Why:** `config.json` will now contain API keys for non-Ollama providers. It should not be committed. The example file serves as documentation and a template for new users.

---

### 1b: Config bootstrap at startup

| File | Change |
|------|--------|
| `src/config.py` | Added `bootstrap_config_if_missing()` — creates `config.json` from `DEFAULT_CONFIG` if it doesn't exist |
| `src/main.py` | Calls `bootstrap_config_if_missing()` at the top of `main_async()` |

**Why:** After a fresh clone, there's no `config.json` (it's in `.gitignore`). The app auto-creates it on first run with sensible Ollama defaults so the user can start immediately.

---

### 1c: Per-role config schema

| File | Change |
|------|--------|
| `src/config.py` | Added `model_config(role)` — reads `models.{role}`, normalizes strings to `{provider, model}` dicts; falls back to hardcoded Ollama defaults. Added `unified_model_config()` — same normalization for `unified_model` key. Added `_normalize_model_value()` helper. Updated `DEFAULT_CONFIG` to full bootstrap default. Marked `unified_model()` as deprecated. Added `_MODEL_DEFAULTS` per-role defaults dict. |

**Config examples supported:**
```jsonc
// String shorthand (backward compat) → {"provider": "ollama", "model": "llama3.1:8b"}
{"models": {"orchestrator": "llama3.1:8b"}}

// Object config → used as-is, provider defaults to "ollama"
{"models": {"orchestrator": {"provider": "openai", "model": "gpt-4o", "api_key": "sk-..."}}}

// Unified override → all roles use same model
{"unified_model": {"provider": "openai", "model": "gpt-4o", "api_key": "sk-..."}}
```

---

### 1d: model_factory.py

| File | Change |
|------|--------|
| `src/model_factory.py` | **New** — `create_llm(config, callbacks)` dispatches by `provider` key. Provider dispatch table with lazy imports. Kwarg filtering per provider with allowlists. Unknown kwargs silently dropped (debug log). Default `base_url` applied for OpenAI-compat providers. |

**Supported providers (Phase 1):**

| Provider | Class | Kwargs allowed |
|----------|-------|---------------|
| `ollama` | `ChatOllama` | model, temperature, stop, callbacks, num_ctx, keep_alive |
| `openai` | `ChatOpenAI` | model, temperature, stop, callbacks, base_url, api_key, max_tokens, top_p |

---

### 1e: Wire into Agents class

| File | Change |
|------|--------|
| `src/agents.py` | Replaced 3 hardcoded `ChatOllama()` calls with `create_llm()`. Imports now use `model_config`, `unified_model_config` instead of `get_model`, `unified_model`. Constructor simplified — removed `model`, `vision_model`, `temperature` params (config-driven), kept `**kwargs` for backward compat. Tracks `_active_providers` set for shutdown decisions. `shutdown()` only unloads Ollama models if at least one role uses Ollama provider. `general_llm` property type hint changed from `ChatOllama` to `BaseChatModel`. |

---

### 1f: main.py bootstrap call

| File | Change |
|------|--------|
| `src/main.py` | Imports `bootstrap_config_if_missing`; calls it as first line of `main_async()`. |

---

### 1g: requirements.txt

| File | Change |
|------|--------|
| `requirements.txt` | Added `langchain-openai>=0.3.0` |

---

### 1h: Tests

| File | Change |
|------|--------|
| `tests/test_model_factory.py` | **New** — 8 unit tests: ollama returns ChatOllama, openai returns ChatOpenAI, unknown provider raises, num_ctx passthrough/dropped, callbacks attached, kwarg filtering for both providers |
| `tests/test_config.py` | Added 12 unit tests: model_config string/object/missing/defaults, unified_model_config string/object/null/missing, bootstrap creates/skips/default-content |
| `tests/test_agents.py` | Added 4 unit tests: string config → ollama, openai config → openai, unified overrides all roles, shutdown skips ollama when not in use. Updated main() to include new tests. |

---

## Rollback Safety

Every change is backward compatible:
- String model values (`"models": {"orchestrator": "llama3.1:8b"}`) → treated as Ollama (identical behavior to before)
- `unified_model` string or null → works as before
- Old `Agents(model=..., vision_model=...)` kwargs → silently accepted via `**kwargs`
- Old `config.json` without `models.router` → router falls back to same model as orchestrator
- `unified_model()` accessor kept (deprecated) for any external callers

---

## What Is NOT Changed (Out of Scope)

| Component | Status |
|-----------|--------|
| `Router.route()` | No changes — uses `BaseChatModel.ainvoke()`, provider-agnostic |
| `Executor.execute()` | No changes — calls `.ainvoke()` on LangGraph agents |
| `Pipeline.process()` | No changes |
| `History.*` | No changes |
| `Formatter.*` | No changes |
| MCP tools (`src/tools/*`) | No changes — vision skill's direct `ollama.chat()` unchanged |
| Prompts (`prompts/*`) | No changes |
| Voice (`src/voice.py`) | No changes |

---

## Test Results

| Suite | Status | Checks | Time |
|-------|--------|--------|------|
| test_application | PASS | ~13 | 0.4s |
| test_config | PASS | ~28 | 1.1s |
| test_extractor | PASS | ~12 | 0.3s |
| test_formatter | PASS | ~12 | 0.0s |
| test_fuzzy_match | PASS | ~15 | 0.0s |
| test_handlers | PASS | ~2 | 0.5s |
| test_history | PASS | ~16 | 0.3s |
| **test_model_factory** | **PASS** | **~8** | **0.5s** |
| test_package_manager | PASS | ~4 | 0.3s |
| test_router | PASS | ~11 | 0.7s |
| test_skill_manifest | PASS | ~11 | 1.1s |
| test_skill_registry | PASS | ~4 | 0.0s |
| test_web_search | PASS | ~4 | 11.3s |
| **Unit total** | **13/13** | **~140** | **16.5s** |
| test_agents (unit + integration) | PASS | ~7 | 2.8s |

---

## Subagent Perspectives

### Python Expert

**Praise.**
- The `model_factory.py` dispatch pattern with lazy imports is clean and future-proof — adding DeepSeek/Qwen/OpenRouter in Phase 2 is a one-line addition to the `_PROVIDERS` dict plus reusing the `"openai"` kwarg allowlist.
- Kwarg filtering per provider is the right abstraction. `ChatOllama` and `ChatOpenAI` have incompatible constructor signatures — silently dropping unknown kwargs prevents `TypeError` at construction time with a debug log for observability.
- The `_normalize_model_value()` helper handles string, dict, None, and edge cases (empty strings, whitespace) in one place. Both `model_config()` and `unified_model_config()` reuse it.

**Flag.**
- `model_config()` re-reads `load_config()` on every call. In the agents constructor, it's called 3 times sequentially — each call re-parses `config.json`. Consider caching or passing the parsed config dict through.
- The `create_llm()` callbacks parameter is a `list | None` but the internal kwarg filtering sets `filtered["callbacks"] = callbacks` only if callbacks is truthy. This means callbacks can't be set to an empty list (minor edge case).
- `_MODEL_DEFAULTS` is a module-level dict — if someone mutates the returned `dict(_MODEL_DEFAULTS[...])` copy and expects it to affect future calls, they'll be confused. The `.copy()` in `model_config()` when falling back is correct, but worth documenting.

**Suggest.** Phase 2 should be straightforward — add `"deepseek"`, `"qwen"`, `"openrouter"` to `_PROVIDERS` with `ChatOpenAI` and appropriate default `base_url` values. All three reuse the `"openai"` kwarg allowlist. No code changes needed to agents or config.

### OS/Linux Expert

**Praise.**
- The `config.json` untracking + bootstrap pattern matches how systemd service files work — `/etc/default/` contains user-editable config, never committed. The example file serves as documentation.
- `bootstrap_config_if_missing()` is a clean atomic operation — checks existence before writing, no race condition in single-process context.
- The default `base_url` for OpenAI (`https://api.openai.com/v1`) is industry standard — users can override it via per-role config for proxies or Azure endpoints.

**Flag.**
- `config.json` permissions not checked — will be world-readable by default (644). API keys in a world-readable file in the project root could be exposed to other local users. Consider checking file permissions on load or documenting `chmod 600 config.json`.
- The vision skill still uses raw `ollama.chat()` for image analysis — if someone configures `"vision": {"provider": "openai", "model": "gpt-4o"}`, the agent LLM will be OpenAI but the actual image analysis call will fail because `_analyze_image()` hardcodes `ollama.chat()`. This is a Phase 2+ concern per the plan.

**Suggest.** Add a permissions check to `load_config()` — warn if config.json is world-readable and contains `api_key`.

### Security Expert

**Praise.**
- API keys live in the untracked `config.json` — not committed, not in environment variables that child processes can read. This follows the principle of least exposure.
- The kwarg filtering in `model_factory.py` is a defense-in-depth measure — even if someone accidentally includes sensitive kwargs in their config, they won't leak to LangChain classes that shouldn't receive them.
- The bootstrap function only writes when the file doesn't exist — no risk of overwriting user config.

**Flag.**
- `config.json` is world-readable by default (644) — API keys exposed to any local user. File permissions should be restricted to 600.
- Lazy imports (`importlib.import_module`) have no validation that the module hasn't been tampered with — a supply-chain concern, but mitigated by the fact that only known LangChain packages are in the dispatch table.
- The vision skill's direct `ollama.chat()` call sends base64-encoded images — no size limit check before encoding. Large screenshots could consume significant memory.

**Suggest.** Add a `chmod 600` to the bootstrap function; add a size check in `_analyze_image()` before base64 encoding; document that API keys should use environment variables or a secrets manager for production deployments.

### AI Integration Expert

**Praise.**
- The 12 new tests are well-structured — unit tests mock `create_llm` correctly, avoiding the need for both `langchain-ollama` and `langchain-openai` to be installed. The integration tests (test_agents) verify the real Ollama path still works.
- The test for `test_shutdown_skips_ollama_when_not_in_use` is particularly valuable — it verifies the shutdown guard works without actually importing the `ollama` library.
- Test structure follows the existing pattern — individual functions with print-based assertions, compatible with `run_tests.py`.

**Flag.**
- The new agents unit tests import `Agents` inside `with patch(...)` blocks — this works but means the import is re-executed on each test call. Consider importing once at module level and patching the imported reference.
- No integration test for the OpenAI path — expected since it requires an API key, but worth documenting that OpenAI integration testing is manual only.
- `test_config.py` now has 28 tests — approaching the point where splitting into `test_config.py` + `test_model_config.py` would improve readability.

**Suggest.** Add a `test_model_factory.py` integration test (skipped by default, controlled by env var) that creates a real `ChatOpenAI` with a test API key for smoke testing. Document the skip behavior clearly.

---

## Manual Test Plan

### 1. Compile / import check
```sh
cd "/home/vuszi/Projects/OS assistant"
python3 -c "from src.model_factory import create_llm; print('OK')"
python3 -c "from src.config import model_config, unified_model_config, bootstrap_config_if_missing; print('OK')"
python3 -c "from src.agents import Agents; print('OK')"
```
**Expected:** All three print "OK" with no import errors or warnings.

### 2. Unit tests (no Ollama needed)
```sh
python3 run_tests.py --unit
```
**Expected:** 13/13 suites pass (~140 assertions), including the new `test_model_factory` suite.

### 3. Config bootstrap (fresh start simulation)
```sh
# Backup current config
cp config.json config.json.bak
# Remove it
rm config.json
# Verify bootstrap creates it
python3 -c "
from src.config import bootstrap_config_if_missing, CONFIG_PATH
result = bootstrap_config_if_missing()
assert result is True, 'Bootstrap should create config'
assert CONFIG_PATH.exists(), 'config.json should exist'
print('Bootstrap created config.json: OK')
"
# Verify bootstrap skips existing
python3 -c "
from src.config import bootstrap_config_if_missing
result = bootstrap_config_if_missing()
assert result is False, 'Bootstrap should skip existing'
print('Bootstrap skipped existing: OK')
"
# Restore original
mv config.json.bak config.json
```
**Expected:** First call creates config, second skips. No errors.

### 4. Default config → Ollama (backward compat)
```sh
python3 -c "
from src.config import model_config, unified_model_config
from unittest.mock import patch
with patch('src.config.load_config', return_value={'models': {'orchestrator': 'llama3.1:8b', 'vision': 'qwen3.5:2b'}}):
    assert model_config('orchestrator') == {'provider': 'ollama', 'model': 'llama3.1:8b'}
    assert model_config('vision') == {'provider': 'ollama', 'model': 'qwen3.5:2b'}
    assert unified_model_config() is None
    print('Default config → ollama: OK')
"
```
**Expected:** All assertions pass.

### 5. OpenAI config
```sh
python3 -c "
from src.config import model_config
from unittest.mock import patch
with patch('src.config.load_config', return_value={
    'models': {'orchestrator': {'provider': 'openai', 'model': 'gpt-4o', 'api_key': 'sk-test'}}
}):
    cfg = model_config('orchestrator')
    assert cfg['provider'] == 'openai'
    assert cfg['model'] == 'gpt-4o'
    assert cfg['api_key'] == 'sk-test'
    print('OpenAI config: OK')
"
```
**Expected:** All assertions pass.

### 6. Integration test (needs Ollama running)
```sh
python3 tests/test_agents.py
```
**Expected:** All 7 tests pass — 4 unit (mocked) + 3 integration (real Ollama). The General and Vision agents should both be `CompiledStateGraph` instances.

### 7. pip install check
```sh
pip install -r requirements.txt 2>&1 | tail -5
```
**Expected:** No errors. `langchain-openai` should install successfully.

### 8. Edge case: unknown provider
```sh
python3 -c "
from src.model_factory import create_llm
try:
    create_llm({'provider': 'nonexistent', 'model': 'foo'})
    print('FAIL: should have raised')
except ValueError as e:
    print(f'Correctly raised ValueError: {e}')
"
```
**Expected:** Raises `ValueError` with message containing `"nonexistent"` and listing supported providers.

### 9. Edge case: OpenAI with Ollama-only kwargs
```sh
python3 -c "
from unittest.mock import MagicMock, patch
from src.model_factory import create_llm
mock_cls = MagicMock(return_value=MagicMock())
with patch('src.model_factory._import_class', return_value=mock_cls):
    create_llm({
        'provider': 'openai', 'model': 'gpt-4o', 'api_key': 'sk-test',
        'num_ctx': 4096, 'keep_alive': 0,  # Ollama-only
    })
    kwargs = mock_cls.call_args[1]
    assert 'num_ctx' not in kwargs, 'num_ctx should be filtered for openai'
    assert 'keep_alive' not in kwargs, 'keep_alive should be filtered for openai'
    print('OpenAI kwarg filtering: OK')
"
```
**Expected:** Ollama-only kwargs silently dropped.

---

## Verdict

Phase 1 of `PLAN_MULTI_PROVIDER.md` is complete. The assistant now supports Ollama and OpenAI LLMs with per-role configuration, automatic config bootstrap, and a clean factory pattern for extension. All 13 unit test suites pass (140 assertions). Backward compatibility is preserved — existing `config.json` files work identically with zero changes needed. The foundation is laid for Phase 2 (DeepSeek, Qwen, OpenRouter) which will be a one-line addition per provider to the dispatch table.
