# Executive Summary — 2026-05-25

## Changes Executed

### Bug fix: GUI apps silently fail to open through MCP pipeline
**Root cause**: Phase 2 of `PLAN_DEP_SECURITY.md` restricted the MCP subprocess environment to only `PATH`, `HOME`, `DBUS_SESSION_BUS_ADDRESS`, `LANG`. This removed `WAYLAND_DISPLAY`, `DISPLAY`, `XDG_RUNTIME_DIR`, etc. — which GUI apps launched via `subprocess.Popen` inherit and need to find the compositor/display.

**Fix**: Added display vars to the whitelist (`DISPLAY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, `XDG_SESSION_TYPE`, `XDG_CURRENT_DESKTOP`).

### Prevention plan executed
Three layers of protection against recurrence:

1. **`src/agents.py`**: Extracted `MCP_ENV_KEYS` as a module-level constant with comments explaining each var's purpose and the full Popen chain trace
2. **`tests/test_config.py`**: Added `test_mcp_required_env_keys()` — a canary test that asserts all required env keys are present (fails if someone removes a key without updating the test)
3. **`AGENTS.md`**: Updated "MCP subprocess env" gotcha with flow-trace instructions and a reference to the canary test

### Files modified
| File | Change |
|------|--------|
| `src/agents.py` | Extracted `MCP_ENV_KEYS` constant with justification comments; `start()` uses it instead of inline list |
| `tests/test_config.py` | Added `test_mcp_required_env_keys()` canary test |
| `tests/test_executor.py` | Removed duplicate env keys test (moved to test_config.py) |
| `AGENTS.md` | Updated "MCP subprocess env" gotcha with full flow-trace instructions + test reference |
| `SECURITY_AUDIT.md` | Updated env whitelist snippet to show full key list |
| `EXECUTIVE_SUMMARY.md` | This file (regenerated per change-cycle rule) |

## Subagent Perspectives

### Python Expert
**Praise**: Extracting `MCP_ENV_KEYS` to a module-level constant is idiomatic — point of change is centralized, importable by tests. The canary test uses set math to be future-proof.
**Flag**: `test_config.py` now imports from `src.agents` — creates a circular-appearing dependency (config test → agents → config). In practice, both are leaf imports, but future refactors should watch this.

### OS/Linux Expert
**Praise**: The env vars chosen are exactly what a Wayland desktop needs: `WAYLAND_DISPLAY` + `XDG_RUNTIME_DIR` for native Wayland, `DISPLAY` for XWayland fallback. `XDG_SESSION_TYPE` and `XDG_CURRENT_DESKTOP` tell apps how to behave.
**Suggest**: Consider `GDK_BACKEND=wayland` if GTK apps need forcing. Also verify `QT_QPA_PLATFORM=wayland` works through env inheritance for Qt apps.

### Security Expert
**Praise**: The whitelist approach is sound — 9 vars instead of full `os.environ`. Each var has a documented runtime purpose.
**Flag**: `DISPLAY` is included for XWayland fallback but on some setups it may not be set — the `if k in os.environ` guard handles that gracefully.
**Suggest**: Periodic audit of `MCP_ENV_KEYS` — as new tools add new Popen/DBus child processes, they may need new env vars. The canary test is the first line of defense.

### AI Integration Expert
**Praise**: Moving the canary test to `test_config.py` (always unit) was correct — `test_executor.py` is classified as integration-only and `--unit` skips it entirely.
**Flag**: `test_executor.py` still mixes unit tests (`_FakeAgent` tests) with integration tests (Ollama-dependent). Consider splitting into `test_executor_unit.py` and `test_executor_integration.py`, or making `run_tests.py` aware of per-function tags. Low priority.

## Manual Test Plan

1. **Run unit tests** — verify canary test passes:
   ```sh
   source .venv/bin/activate && python3 run_tests.py --unit
   ```
   Expected: 11/11 suites pass, `MCP_ENV_KEYS: all required + no dupes: OK` visible under test_config.

2. **Verify canary catches missing keys** — temporarily remove `WAYLAND_DISPLAY` from `MCP_ENV_KEYS` in `src/agents.py`, re-run unit tests:
   ```sh
   source .venv/bin/activate && python3 tests/test_config.py
   ```
   Expected: assertion fails with `Missing required keys from MCP_ENV_KEYS: {'WAYLAND_DISPLAY'}`. Undo the edit afterwards.

3. **Verify app opens through MCP pipeline** — full end-to-end:
   ```sh
   source .venv/bin/activate && python3 -m src.main
   ```
   Then type: "Open Firefox"
   Expected: Firefox window appears, assistant responds "Firefox has been opened."

4. **Run integration tests** (needs Ollama running):
   ```sh
   source .venv/bin/activate && python3 run_tests.py --integration
   ```
   Expected: 4/4 suites pass (test_agents, test_executor, test_pipeline, test_close).
