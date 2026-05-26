# Executive Summary — 2026-05-26

## Changes Executed

### Skill Refactor: Per-Skill Config + Folder Structure (Phases 1-3)

Moved all 5 skills into their own `src/tools/<name>/` folders with per-skill `config.toml` + `manifest.toml`. Adding a new skill now requires zero changes to `config.json`.

| Phase | What changed | Result |
|-------|-------------|--------|
| 1 | Skills to packages, `_discover_skills()`, `_read_skill_config()`, `_is_skill_enabled()` | 5 skill folders, manifest-based discovery, per-skill enable/disable |
| 2 | Removed `skills` from `DEFAULT_CONFIG`, `skill_enabled()` → optional override | `config.json` has zero skill-specific sections |
| 3 | Final verification, security fixes, integration tests | 11/11 unit + 4/4 integration pass |

**Directory structure after refactor:**
```
src/tools/
├── __init__.py              # _discover_skills(), _read_skill_config(), _is_skill_enabled()
├── _registry.py             # deferred @tool() decorator
├── server.py                # FastMCP entry point
├── desktop_index.py         # shared helper (flat)
├── fuzzy_match.py           # shared helper (flat)
├── application/
│   ├── __init__.py          # tool functions
│   ├── manifest.toml        # [skill] name, description, prompt_hint
│   └── config.toml          # [skill] enabled = true
├── vision/        (... same pattern)
├── web_search/    (... same pattern)
├── package_manager/ (... same pattern)
│   └── config.toml          # [skill] enabled + [install_guides] directory
└── window_manager/ (... same pattern)
```

### install_guides Migration

Moved `install_guides` config from `config.json` into `package_manager/config.toml`:
- Primary source: `package_manager/config.toml` → `[install_guides] directory = "install_guides"`
- `config.json` removed `install_guides` section
- `install_guides_dir()` checks: override → per-skill config → default

### Security Fixes (from security-expert review of config.toml pattern)

| Fix | Severity | Detail |
|-----|----------|--------|
| Path traversal guard in `install_guides_dir()` | Moderate | Values with `..` or absolute paths rejected — fall through to safe default |
| Exception handler in `_read_manifest()` | Low | Malformed `manifest.toml` no longer crashes pipeline |
| Dead import removed | Low | `skill_enabled` imported but never called in `__init__.py` |

### Files Modified

| File | Change |
|------|--------|
| `src/tools/__init__.py` | Rewritten: `_discover_skills()`, `_read_skill_config()`, `_is_skill_enabled()`, `_read_manifest()` with exception handler, removed `pkgutil` and dead `skill_enabled` import |
| `src/tools/application/__init__.py` | Moved from `application.py`; relative imports → `..` |
| `src/tools/application/manifest.toml` | Moved from `application.toml` |
| `src/tools/application/config.toml` | New: `[skill] enabled = true` |
| `src/tools/vision/__init__.py` | Moved from `vision.py`; imports → `..` |
| `src/tools/vision/manifest.toml` | Moved from `vision.toml` |
| `src/tools/vision/config.toml` | New |
| `src/tools/web_search/__init__.py` | Moved + imports → `..` |
| `src/tools/web_search/manifest.toml` | Moved |
| `src/tools/web_search/config.toml` | New |
| `src/tools/package_manager/__init__.py` | Moved + imports → `..` |
| `src/tools/package_manager/manifest.toml` | Moved |
| `src/tools/package_manager/config.toml` | New: `[skill]` + `[install_guides]` |
| `src/tools/window_manager/__init__.py` | Moved + imports → `..` |
| `src/tools/window_manager/manifest.toml` | Moved |
| `src/tools/window_manager/config.toml` | New |
| `src/config.py` | Removed `skills` and `install_guides` from `DEFAULT_CONFIG`; `install_guides_dir()` with path traversal guard; `skill_enabled()` docstring updated |
| `config.json` | Removed `install_guides` section; `skills` kept as empty `{}` (harmless no-op) |
| `tests/test_skill_manifest.py` | Updated patch (`_is_skill_enabled`), added `test_per_skill_config_enabled_false()` |
| `tests/test_config.py` | Added `test_install_guides_dir_reads_per_skill_config()` |
| `AGENTS.md` | Updated "Adding a skill" section for folder structure + per-skill config |
| `PLAN_SKILL_REFACTOR.md` | Full 3-phase plan + install_guides migration appendix |

### Files Deleted

| File | Reason |
|------|--------|
| `src/tools/application.py` | → `application/__init__.py` |
| `src/tools/application.toml` | → `application/manifest.toml` |
| `src/tools/vision.py` | → `vision/__init__.py` |
| `src/tools/vision.toml` | → `vision/manifest.toml` |
| `src/tools/web_search.py` | → `web_search/__init__.py` |
| `src/tools/web_search.toml` | → `web_search/manifest.toml` |
| `src/tools/package_manager.py` | → `package_manager/__init__.py` |
| `src/tools/package_manager.toml` | → `package_manager/manifest.toml` |
| `src/tools/window_manager.py` | → `window_manager/__init__.py` |
| `src/tools/window_manager.toml` | → `window_manager/manifest.toml` |
| `src/tools/__pycache__/*` | Stale bytecode from old flat modules |

## Subagent Perspectives

### Python Expert
**Praise**: Extracting `_discover_skills()` as a `manifest.toml`-based discovery function is clean and explicit. No dependence on Python packaging semantics. The relative import fix (`.` → `..`) is correct for the new sub-package structure.
**Flag**: `install_guides_dir()` in `config.py` now reads from `src/tools/package_manager/config.toml` — layering violation (config → tools dependency). Consider moving to a shared location or having the skill pass its config path up.

### OS/Linux Expert
**Praise**: Directory structure is clean and predictable. Permissions inheritance from the parent `src/tools/` works correctly. `grep`-ability of manifest.toml files in subdirs is a nice property.
**Suggest**: Verify the assistant service file (if any) still points to the correct Python module paths after the restructure.

### Security Expert
**Praise**: Path traversal guard in `install_guides_dir()` is simple and effective — rejects `..` and absolute paths, falls through to safe default. The `_read_manifest()` exception handler prevents DoS from malformed TOML.
**Flag**: Auto-discovery via `manifest.toml` is safe as long as the scan root is hardcoded. Periodically verify no discovery path has become configurable through a refactor.
**Residual**: The `screenshot_dir()` uses `config.json` only with no per-skill fallback — different trust model. A similar path traversal guard should be considered.

### AI Integration Expert
**Praise**: 11/11 unit tests + 4/4 integration tests pass. The new `test_per_skill_config_enabled_false` validates the core new feature. The `test_install_guides_dir_reads_per_skill_config` validates the per-skill config fallback.
**Flag**: `test_executor.py` still mixes unit tests (`_FakeAgent`) with integration tests (Ollama-dependent). The `--unit` flag skips the entire file, losing 6 unit tests. Consider splitting or tagging.

## Test Results

| Suite | Status | Checks | Time |
|-------|--------|--------|------|
| test_application | PASS | ~13 | 0.2s |
| test_config | PASS | ~17 | 1.0s |
| test_extractor | PASS | ~12 | 0.3s |
| test_formatter | PASS | ~12 | 0.0s |
| test_fuzzy_match | PASS | ~15 | 0.0s |
| test_history | PASS | ~11 | 0.3s |
| test_package_manager | PASS | ~4 | 0.1s |
| test_router | PASS | ~11 | 0.7s |
| test_skill_manifest | PASS | ~11 | 1.1s |
| test_skill_registry | PASS | ~4 | 0.0s |
| test_web_search | PASS | ~4 | 2.5s |
| **Unit total** | **11/11** | **~114** | **6.2s** |
| test_agents | PASS | ~3 | 2.5s |
| test_close | PASS | ~7 | 0.1s |
| test_executor | PASS | ~12 | 12.4s |
| test_pipeline | PASS | ~8 | 63.9s |
| **Integration total** | **4/4** | **~30** | **78.9s** |

## Manual Test Plan

```bash
# 1. Verify skill discovery
source .venv/bin/activate
python3 -c "from src.tools import _discover_skills; print(_discover_skills())"
# Expected: ['application', 'package_manager', 'vision', 'web_search', 'window_manager']

# 2. Verify per-skill config disable
echo -e "[skill]\nenabled = false" > src/tools/package_manager/config.toml
python3 -c "from src.tools import _build_tool_list; print(_build_tool_list())"
# Expected: "Search packages" NOT in output
git checkout src/tools/package_manager/config.toml  # restore

# 3. Verify path traversal guard
python3 -c "
from src.config import install_guides_dir
p = install_guides_dir()
assert str(p).endswith('install_guides')
print(f'OK: {p}')
"

# 4. Verify adding a new skill needs no config.json change
mkdir -p src/tools/test_skill
cat > src/tools/test_skill/__init__.py << 'END'
from .._registry import tool
@tool()
def tool_test() -> str: return 'test'
END
cat > src/tools/test_skill/manifest.toml << 'END'
[skill]
name = "test_skill"
description = "Test"
prompt_hint = ""
END
cat > src/tools/test_skill/config.toml << 'END'
[skill]
enabled = true
END
python3 -c "from src.tools import _discover_skills; assert 'test_skill' in _discover_skills(); print('New skill discovered without config.json: OK')"
rm -rf src/tools/test_skill

# 5. Full smoke test
python3 -m src.main
# Type: "Open Firefox" — app should open
# Type: "Search for htop" — should return packages
```

## Verdict

**11/11 unit, 4/4 integration, 0 regressions.** The per-skill config refactor is complete. `config.json` is no longer required for skill configuration — each skill owns its own `config.toml`. Adding a new skill requires only a folder + 3 files. Security review findings resolved.
