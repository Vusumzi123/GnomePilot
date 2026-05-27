# Executive Summary — 2026-05-26

## Changes Executed

### Skill Refactor: Per-Skill Config + Folder Structure

Moved all 5 skills into their own `src/tools/<name>/` folders with per-skill `config.toml` + `manifest.toml`. Adding a new skill now requires zero changes to `config.json`.

### install_guides Migration

Moved `install_guides` config from `config.json` into `package_manager/config.toml`. Path traversal guard added.

### Unavailable Handlers

Every skill now exports an `async def handler(input, config=None)` that returns a clear "not available" message when disabled. Messages configurable via `manifest.toml` `unavailable_message`. The vision agent uses the handler instead of creating a crippled LangGraph agent when `tool_capture_screen` is not registered.

### Vision Prompt Simplification

`prompts/vision.md` updated with stronger imperative instructions: "ALWAYS use the screenshot tool first — never respond without capturing the screen" and "Take the screenshot immediately — do not ask for permission or confirm first".

### Security Fixes

- Path traversal guard in `install_guides_dir()` — rejects `..` and absolute paths
- Exception handler in `_read_manifest()` — malformed TOML doesn't crash pipeline
- Dead `skill_enabled` import removed from `__init__.py`

## Test Results

| Suite | Status | Checks | Time |
|-------|--------|--------|------|
| test_application | PASS | ~13 | 0.4s |
| test_config | PASS | ~17 | 1.1s |
| test_extractor | PASS | ~12 | 0.3s |
| test_formatter | PASS | ~12 | 0.0s |
| test_fuzzy_match | PASS | ~15 | 0.0s |
| test_handlers | PASS | ~2 | 0.5s |
| test_history | PASS | ~11 | 0.3s |
| test_package_manager | PASS | ~4 | 0.3s |
| test_router | PASS | ~11 | 0.7s |
| test_skill_manifest | PASS | ~11 | 1.1s |
| test_skill_registry | PASS | ~4 | 0.0s |
| test_web_search | PASS | ~4 | 4.3s |
| **Unit total** | **12/12** | **~116** | **8.9s** |
| test_agents | PASS | ~3 | 2.5s |
| test_close | PASS | ~7 | 0.1s |
| test_executor | PASS | ~12 | 12.4s |
| test_pipeline | PASS | ~8 | 63.9s |
| **Integration total** | **4/4** | **~30** | **78.9s** |

---

## Subagent Perspectives

### Python Expert

**Praise.**
- The `@tool()` deferred registry in `src/tools/_registry.py` is elegantly minimal — 14 lines of actual logic avoids per-skill boilerplate. Auto-discovery filtering by `manifest.toml` presence is clean.
- Pipeline pattern (`Enrich → Route → Build → Execute → Format → Store`) is well-composed. Each stage maps to a single-responsibility class wired via a typed `Context` dataclass.
- Deferred imports in `src/executor.py:25` and `src/tools/package_manager/__init__.py:69` correctly avoid compile-time circular dependencies.

**Flag.**
- Every skill module repeats ~30 lines of identical boilerplate for `handler()` and manifest loading. Extract into a `_registry.create_handler()` factory — duplication will grow with every new skill.
- `src/agents.py:18-22` hardcodes per-skill handler imports at module level, contradicting the auto-discovery design. Have `src/tools/__init__.py` export a `HANDLERS` dict populated during `_discover_skills()` instead.
- Broad `except Exception` with no logging in at least 6 places (`src/tools/__init__.py:54`, `src/router.py:80`, `src/config.py:114`, `src/agents.py:142`, `src/formatter.py`). A broken manifest silently disables a skill.
- `async def handler` in all 5 skill modules but contains no `await` — misleading signature. Make plain `def` or document intentional.
- `src/config.py` calls `load_config()` on every accessor (20+ times per request). Use `functools.cached_property` or a `Config` singleton.

**Suggest.** Cache the config dict; rename `_safe_dir()` to `_resolve_dir()` to separate validation from filesystem side effects.

### OS/Linux Expert

**Praise.**
- Screenshot capture uses XDG Desktop Portal (`org.freedesktop.portal.Screenshot`) — the only Wayland-viable method. DBus signal receiver pattern is correct.
- `validate_desktop_file()` checks zero-size, owner, group/other write bits, distinguishes system vs user directories — unusually thorough for a hobby project.
- `MCP_ENV_KEYS` whitelist is well-chosen and documented — only essential vars leak to the MCP subprocess.
- App launches use `subprocess.Popen` with `stdin/stdout/stderr=DEVNULL`, `close_fds=True`, `start_new_session=True` — prevents child output from corrupting MCP JSON-RPC.

**Flag.**
- No `/var/lib/flatpak/exports/share/applications` in desktop search paths — system Flatpak apps are invisible.
- `yay` subprocess passes full `dict(os.environ)` in `package_manager/__init__.py:54`, bypassing the `MCP_ENV_KEYS` whitelist while `pacman` doesn't — inconsistent security boundary.
- `validate_desktop_file()` doesn't call `path.resolve()` before `stat()` — symlinks (common for Flatpak `.desktop` entries) are judged by the symlink's permissions, not the target's.
- No `shutil.which("yay")` pre-check — `FileNotFoundError` propagates instead of a clean "AUR helper not found" message.
- `_WINDOWS_BUS` (application) and `_WIN_BUS` (window_manager) are the same constant defined twice — extract to shared module.

**Suggest.** Add `XDG_DATA_DIRS` and `XDG_DATA_HOME` to `MCP_ENV_KEYS`; use `Gio.DesktopAppInfo.search()` for spec-compliant app discovery.

### Security Expert

**Praise.**
- All subprocess calls are list-based (`no shell=True`) — zero shell injection surface.
- `validate_desktop_file()` correctly requires root-owned files in system dirs and current-user ownership elsewhere, rejecting group/other-writable files. Called before every `subprocess.Popen` launch.
- `install_guides_dir()` has a `_safe_dir()` guard rejecting `..` and absolute paths — keeps output within `PROJECT_DIR`.
- `MCP_ENV_KEYS` whitelist is tight (9 vars), well-documented, and only forwards keys that exist in the parent env.
- `tomllib` (stdlib) is used for all TOML parsing — no deserialization RCE risk. `_read_manifest()` wrapped in try/except.

**Flag.**
- Field code stripping regex at `desktop_index.py:132` is incomplete — misses freedesktop codes `%d`, `%n`, `%N`, `%v`, `%m`, `%D`. Leftover field codes become literal arguments to `shlex.split`.
- `screenshot_dir()` has **no traversal guard** — accepts any path from `config.json` without `..` or symlink checks.
- `_install_package()` sanitizes `package_name` only for the filename, not the generated markdown body — LLM-suggested malicious package names appear unquoted in the install guide.
- `importlib.import_module()` in `register_all()` executes arbitrary Python in any `__init__.py` under `src/tools/` — no integrity check. Acceptable for local-only but worth documenting.
- Web search has no `max_results` clamp — type hint says 1–10 but runtime enforces nothing (`web_search/__init__.py:32`).

**Suggest.** Expand field code regex to `r'(?<!=)%[uUfFkciDdNnmv]|%%'`; apply `_safe_dir()` guard to `screenshot_dir()`; sanitize package names in install guide body.

### AI Integration Expert

**Praise.**
- Executor dedup tests are excellent: three dedup tests + two false-positive tests (different args, different names) — among the best defensive tests in the suite.
- Router regex-on-original / LLM-on-enriched separation is well-designed and correctly tested — history words don't leak into regex matching.
- Formatter test coverage is comprehensive (12 tests): emojis, zero-width chars, BOM, MCP tool-call JSON, markdown fences, whitespace.
- `prompts/general.md` line 15 ("Call each tool ONCE only. Do not retry.") paired with executor dedup creates defense-in-depth against LLM looping.
- `test_mcp_required_env_keys` is a canary test with thorough docstring — prevents the historically-occurring silent display-vars failure.

**Flag.**
- `test_executor.py` and `test_pipeline.py` have ~16 unit tests (mock-only, fast) that are invisible to `--unit` runs — both files are classified as integration-only in `run_tests.py:22`.
- No integration test for Router with a real LLM — all router tests use `FakeLLM`. The `prompts/router.md` is never validated against actual LLM output.
- Agent tool split (`agents.py:110-111`) has zero test coverage — no assertion verifies vision got exactly 1 tool and general got the rest.
- No test for `GraphRecursionError` recovery in the pipeline — the user-friendly fallback message is untested.
- The chain context prefix at `executor.py:59` ("Context from vision analysis (already completed)") is a magic string duplicated in executor and general prompt — fragile contract.

**Suggest.** Split `test_executor.py` and `test_pipeline.py` so unit subtests run under `--unit`; add a Router LLM integration test; make the chaining prefix a module-level constant exported from `executor.py`.

---

## Verdict

12/12 unit, 4/4 integration, 0 regressions. `config.json` is no longer required for skill configuration. Adding a skill needs zero config.json edits. Disabled skills return clear "not available" messages. The vision prompt now mandates immediate screenshot capture.
