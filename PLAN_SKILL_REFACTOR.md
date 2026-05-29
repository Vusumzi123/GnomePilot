# Plan: Per-Skill Config + Folder Structure

## Goal
Move each skill into its own `src/tools/<name>/` folder with its own `config.toml` + `manifest.toml`, so adding a new skill never requires touching `config.json`. Apply the same pattern to skill-specific config like `install_guides` — each skill owns its own settings.

## Current vs Target Structure

```
BEFORE                              AFTER
src/tools/                          src/tools/
├── __init__.py                     ├── __init__.py          # updated discovery
├── _registry.py                    ├── _registry.py         # unchanged
├── server.py                       ├── server.py            # unchanged
├── application.py     ──move──►    ├── application/
├── application.toml   ──move──►    │   ├── __init__.py
│                                   │   ├── manifest.toml
│                                   │   └── config.toml        NEW
├── vision.py          ──move──►    ├── vision/
├── vision.toml        ──move──►    │   ├── __init__.py
│                                   │   ├── manifest.toml
│                                   │   └── config.toml        NEW
├── web_search.py      ──move──►    ├── web_search/
├── web_search.toml    ──move──►    │   ├── __init__.py
│                                   │   ├── manifest.toml
│                                   │   └── config.toml        NEW
├── package_manager.py ──move──►    ├── package_manager/
├── package_manager.toml─move──►    │   ├── __init__.py
│                                   │   ├── manifest.toml
│                                   │   └── config.toml        NEW
├── window_manager.py  ──move──►    ├── window_manager/
├── window_manager.toml─move──►     │   ├── __init__.py
│                                   │   ├── manifest.toml
│                                   │   └── config.toml        NEW
├── desktop_index.py                ├── desktop_index.py       # stays flat (shared helper)
├── fuzzy_match.py                  └── fuzzy_match.py         # stays flat (shared helper)
```

**Shared helpers** (`desktop_index.py`, `fuzzy_match.py`) stay as flat files at `src/tools/` — they are internal utilities used by skills but are not skills themselves. They have no `@tool()` decorators and no `.toml` manifests. Skill discovery ignores them naturally via `manifest.toml` existence check.

---

## Phase 1: Skills to packages + per-skill config

### Objectives
- Move each of the 5 skills into its own folder under `src/tools/`
- Add per-skill `config.toml` with `enabled = true` default
- Update skill discovery to use `manifest.toml` existence instead of `pkgutil.iter_modules`
- Add `_read_skill_config()` and `_is_skill_enabled()` to `src/tools/__init__.py`
- All existing tests still pass

### Files to create

| File | Content |
|------|---------|
| `src/tools/application/__init__.py` | **Move** from `src/tools/application.py` (no content changes) |
| `src/tools/application/manifest.toml` | **Move** from `src/tools/application.toml` |
| `src/tools/application/config.toml` | `[skill]\nenabled = true` |
| `src/tools/vision/__init__.py` | **Move** from `src/tools/vision.py` |
| `src/tools/vision/manifest.toml` | **Move** from `src/tools/vision.toml` |
| `src/tools/vision/config.toml` | `[skill]\nenabled = true` |
| `src/tools/web_search/__init__.py` | **Move** from `src/tools/web_search.py` |
| `src/tools/web_search/manifest.toml` | **Move** from `src/tools/web_search.toml` |
| `src/tools/web_search/config.toml` | `[skill]\nenabled = true` |
| `src/tools/package_manager/__init__.py` | **Move** from `src/tools/package_manager.py` |
| `src/tools/package_manager/manifest.toml` | **Move** from `src/tools/package_manager.toml` |
| `src/tools/package_manager/config.toml` | `[skill]\nenabled = true` |
| `src/tools/window_manager/__init__.py` | **Move** from `src/tools/window_manager.py` |
| `src/tools/window_manager/manifest.toml` | **Move** from `src/tools/window_manager.toml` |
| `src/tools/window_manager/config.toml` | `[skill]\nenabled = true` |

### Files to modify

| File | Changes |
|------|---------|
| `src/tools/__init__.py` | Replace `pkgutil.iter_modules` with `_discover_skills()`. Add `_read_skill_config()`, `_is_skill_enabled()`. Update `_read_manifest()` to read from `<name>/manifest.toml`. Switch all internal loops to use `_discover_skills()` + `_is_skill_enabled()`. |
| `AGENTS.md` | Update "Adding a skill" section for new folder structure |

### Files to delete

| File | Reason |
|------|--------|
| `src/tools/application.py` | Moved to `application/__init__.py` |
| `src/tools/application.toml` | Moved to `application/manifest.toml` |
| `src/tools/vision.py` | Moved to `vision/__init__.py` |
| `src/tools/vision.toml` | Moved to `vision/manifest.toml` |
| `src/tools/web_search.py` | Moved to `web_search/__init__.py` |
| `src/tools/web_search.toml` | Moved to `web_search/manifest.toml` |
| `src/tools/package_manager.py` | Moved to `package_manager/__init__.py` |
| `src/tools/package_manager.toml` | Moved to `package_manager/manifest.toml` |
| `src/tools/window_manager.py` | Moved to `window_manager/__init__.py` |
| `src/tools/window_manager.toml` | Moved to `window_manager/manifest.toml` |
| `src/tools/__pycache__/*` | Stale bytecode from old module paths — delete entire `__pycache__/` |

### Detailed `src/tools/__init__.py` changes

#### New: `_discover_skills()`
```python
def _discover_skills() -> list[str]:
    """Return sorted names of skill packages (dirs containing manifest.toml)."""
    skills = []
    for entry in _TOOLS_DIR.iterdir():
        if entry.is_dir() and not entry.name.startswith("_") \
                and (entry / "manifest.toml").exists():
            skills.append(entry.name)
    return sorted(skills)
```
Replaces all uses of `pkgutil.iter_modules(__path__)` for skill discovery. Only directories with `manifest.toml` are considered skills — `desktop_index.py` and `fuzzy_match.py` are naturally excluded.

#### New: `_read_skill_config()`
```python
def _read_skill_config(name: str) -> dict:
    """Read per-skill config from <name>/config.toml, return [skill] section."""
    config_path = _TOOLS_DIR / name / "config.toml"
    if not config_path.exists():
        return {}
    try:
        return tomllib.loads(config_path.read_text()).get("skill", {})
    except Exception:
        return {}
```

#### New: `_is_skill_enabled()`
```python
def _is_skill_enabled(name: str) -> bool:
    """Whether a skill is enabled. Checks:
    1. Main config.json "skills.<name>" override (if present)
    2. Skill's own config.toml [skill] enabled
    3. Default True
    """
    # Main config override (backward compat)
    cfg = load_config()
    if name in cfg.get("skills", {}):
        return bool(cfg["skills"][name])
    # Per-skill config
    sc = _read_skill_config(name)
    return sc.get("enabled", True)
```
Note: needs `from src.config import load_config` added to imports.

#### Changed: `_read_manifest()`
```python
# OLD: toml_path = _TOOLS_DIR / f"{name}.toml"
# NEW: toml_path = _TOOLS_DIR / name / "manifest.toml"
```

#### Changed: `_build_tool_list()`, `register_all()`, `skill_summary()`
- All three replace `for _, name, _ in pkgutil.iter_modules(__path__)` with `for name in _discover_skills()`
- `register_all()` and `_build_tool_list()` replace `skill_enabled(name)` with `_is_skill_enabled(name)`
- `import pkgutil` can be removed from imports (no longer used)

### Why internal imports don't break
Skill `__init__.py` files import from sibling modules using relative imports:
```python
from .desktop_index import resolve, _read_exec_line, validate_desktop_file
from .fuzzy_match import best as best_match
from ._registry import tool
```
After the move, `application/__init__.py` is a sub-package of `src.tools`. The relative import `.desktop_index` still resolves to `src.tools.desktop_index.py` (the flat file). No import changes needed in the skill source files.

### Why external imports don't break
- `src/tools/server.py` → `from . import register_all` — unchanged
- `src/agents.py` → `from src.tools import _build_tool_list` — unchanged
- Tests → `from src.tools.application import _open_application` — unchanged (Python resolves `src.tools.application` to the package `application/__init__.py` automatically)
- Tests → `from src.tools._registry import tool, collect` — unchanged

### Subagent delegation

| Subagent | Task | Details |
|----------|------|---------|
| `python-expert` | Rewrite `src/tools/__init__.py` | Implement `_discover_skills()`, `_read_skill_config()`, `_is_skill_enabled()`; update `_read_manifest()` path; convert all loops; remove `pkgutil` import |
| `python-expert` | Create 5 skill folders + files | Create directories, move/rename files, create `config.toml` files, delete stale flat files and `__pycache__/` |
| `python-expert` | Update `test_skill_manifest.py` | Patch `src.tools._is_skill_enabled` instead of `src.tools.skill_enabled` in `test_disabled_skill_omitted` |
| `python-expert` | Update `AGENTS.md` | Rewrite "Adding a skill" section for new folder structure |

### Manual testing

```bash
# 1. Verify skill discovery
source .venv/bin/activate
python3 -c "from src.tools import _discover_skills; print(_discover_skills())"
# Expected: ['application', 'package_manager', 'vision', 'web_search', 'window_manager']

# 2. Verify manifest reading from new paths
python3 -c "
from src.tools import _read_manifest
for name in ['application', 'vision']:
    m = _read_manifest(name)
    print(f'{name}: name={m[\"name\"]}, desc={m[\"description\"][:30]}')
"
# Expected: name matches, description present

# 3. Verify config.toml reading
python3 -c "
from src.tools import _read_skill_config, _is_skill_enabled
for name in ['application', 'package_manager']:
    cfg = _read_skill_config(name)
    enabled = _is_skill_enabled(name)
    print(f'{name}: config={cfg}, enabled={enabled}')
"
# Expected: enabled=True for all

# 4. Verify tool descriptions render
python3 -c "from src.tools import _build_tool_list; print(_build_tool_list())"
# Expected: 4 hints (application, package_manager, web_search, window_manager)
# Vision should NOT appear (empty prompt_hint)

# 5. Disable a skill via its config.toml, verify exclusion
cp src/tools/package_manager/config.toml /tmp/pkgmgr_config.bak
echo -e "[skill]\nenabled = false" > src/tools/package_manager/config.toml
python3 -c "from src.tools import _build_tool_list; print(_build_tool_list())"
# Expected: "Search packages" NOT in output
mv /tmp/pkgmgr_config.bak src/tools/package_manager/config.toml

# 6. Run unit tests
python3 run_tests.py --unit
# Expected: 11/11 pass

# 7. Verify MCP server starts
python3 -m src.tools.server 2>&1 &
sleep 2 && kill %1 2>/dev/null
# Expected: no traceback, server process starts and responds

# 8. Clean stale __pycache__ (should have been deleted)
find src/tools -name '__pycache__' -type d
# Expected: only in skill folders (auto-generated), no stale .pyc from old flat files
```

---

## Phase 2: Remove skills from main config + simplify

### Objectives
- Remove `"skills"` from `DEFAULT_CONFIG` in `config.py` — skills no longer need to be listed in the central config
- Keep `skill_enabled()` for config.json override backward compat
- Add test coverage for per-skill `config.toml` enable/disable

### Files to modify

| File | Changes |
|------|---------|
| `src/config.py` | Remove `"skills"` block from `DEFAULT_CONFIG`. Add docstring to `skill_enabled()` documenting it's an optional override. |
| `tests/test_skill_manifest.py` | Add `test_per_skill_config_enabled_false()` — patches `_read_skill_config` to return `{"enabled": False}` and verifies skill is excluded |
| `AGENTS.md` | Update config.json reference — `"skills"` is now optional, per-skill `config.toml` is the recommended way |

### Detailed `src/config.py` changes

`DEFAULT_CONFIG` — remove the `"skills"` block:
```python
DEFAULT_CONFIG = {
    "models": {
        "orchestrator": "llama3.1:8b",
        "vision": "minicpm-v:8b",
    },
    "orchestrator": {
        "temperature": 0,
        "chat_history_size": 10,
        "recursion_limit": 10,
    },
    "install_guides": {
        "directory": "install_guides",
    },
}
```

`skill_enabled()` — add docstring explaining it's the optional main-config override:
```python
def skill_enabled(name: str) -> bool:
    """Check config.json "skills.<name>" override. Returns True if not set.
    
    For per-skill enable/disable, use the skill's own config.toml file.
    This function is a main-config override — the authoritative check is
    _is_skill_enabled() in src.tools.__init__ which reads per-skill config.
    """
    return bool(load_config().get("skills", {}).get(name, True))
```

### New test: `test_per_skill_config_enabled_false`

Added to `tests/test_skill_manifest.py`:
```python
def test_per_skill_config_enabled_false():
    """Skill's own config.toml with enabled=false excludes it."""
    from unittest.mock import patch
    from src.tools import _read_skill_config, _build_tool_list, _is_skill_enabled

    # Mock _read_skill_config to simulate a disabled skill
    def mock_config(name):
        if name == "application":
            return {"enabled": False}
        return {"enabled": True}

    with patch("src.tools._read_skill_config", side_effect=mock_config):
        assert not _is_skill_enabled("application")
        assert _is_skill_enabled("vision")
        lines = _build_tool_list()
        assert "Open and close applications" not in lines
    print("  per-skill config.toml disabled: OK")
```

### Subagent delegation

| Subagent | Task | Details |
|----------|------|---------|
| `python-expert` | Update `src/config.py` | Remove `skills` from `DEFAULT_CONFIG`, update `skill_enabled()` docstring |
| `python-expert` | Add test to `test_skill_manifest.py` | `test_per_skill_config_enabled_false()` — verifies per-skill config controls enable/disable |

### Manual testing

```bash
# 1. Verify DEFAULT_CONFIG no longer has skills
source .venv/bin/activate
python3 -c "
from src.config import DEFAULT_CONFIG
assert 'skills' not in DEFAULT_CONFIG
print('DEFAULT_CONFIG has no skills section: OK')
"

# 2. Verify all skills load without config.json skills section
python3 -c "from src.tools import _build_tool_list; print(_build_tool_list())"
# Expected: all 4 hints appear (per-skill config.toml handles defaults)

# 3. Test main config.json override still works
python3 -c "
import json
from src.config import skill_enabled
# Create a temp override scenario
cfg = {'skills': {'package_manager': False}}
import src.config
with __import__('unittest.mock').patch.object(src.config, 'load_config', return_value=cfg):
    assert not skill_enabled('package_manager')
    print('main config override still works: OK')
"

# 4. Run unit tests
python3 run_tests.py --unit
# Expected: 12/12 pass (new per-skill config test included)

# 5. Verify new test explicitly
python3 tests/test_skill_manifest.py
# Expected: test_per_skill_config_enabled_false: OK
```

---

## Phase 3: Final verification + cleanup

### Objectives
- Full test suite pass (unit + integration)
- Manual smoke test with real assistant
- Regenerate EXECUTIVE_SUMMARY.md per change-cycle rule
- Final AGENTS.md review

### Subagent delegation

| Subagent | Task | Details |
|----------|------|---------|
| `ai-integration` | Run full test suite | `python3 run_tests.py --unit && python3 run_tests.py --integration`, report pass/fail |
| `os-expert` | Verify file permissions + stale cache | Check new directories have correct perms, verify no stale `.pyc` files from old flat modules |
| `security-expert` | Review config.toml pattern | Verify per-skill configs don't expose sensitive paths or escalate permissions |

### Manual testing

```bash
# 1. Full unit test suite
source .venv/bin/activate && python3 run_tests.py --unit
# Expected: all suites pass

# 2. Integration tests (requires Ollama running)
python3 run_tests.py --integration
# Expected: 4/4 pass (test_agents, test_executor, test_pipeline, test_close)

# 3. Clean stale bytecode
find src/tools -name '__pycache__' -path '*src/tools/__pycache__/*' -exec rm -rf {} + 2>/dev/null

# 4. Smoke test — full assistant pipeline
python3 -m src.main
# Type: "Open Firefox"
# Expected: Firefox window appears, assistant responds
# Type: "Close Firefox"
# Expected: Firefox window closes
# Type: "Search the web for Python 3.14 release date"
# Expected: web search returns results

# 5. Verify adding a new skill doesn't touch config.json
# Create a test skill
mkdir -p src/tools/test_skill
cat > src/tools/test_skill/__init__.py << 'PYEOF'
from .._registry import tool

@tool()
def tool_hello() -> str:
    """Say hello."""
    return "hello"
PYEOF
cat > src/tools/test_skill/manifest.toml << 'TOEOF'
[skill]
name = "test_skill"
description = "A test skill"
prompt_hint = "- Say hello"
TOEOF
cat > src/tools/test_skill/config.toml << 'TOEOF'
[skill]
enabled = true
TOEOF

# Verify it's discovered and enabled
python3 -c "from src.tools import _discover_skills, _build_tool_list; print(_discover_skills())"
# Expected: test_skill appears in list
python3 -c "from src.tools import _build_tool_list; print(_build_tool_list())"
# Expected: "- Say hello" appears

# Cleanup
rm -rf src/tools/test_skill
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Relative imports break when `.py` files become `__init__.py` in sub-packages | Medium | Import paths don't change — `.fuzzy_match` still resolves to `src.tools.fuzzy_match`. Python resolves relative imports up the package hierarchy. |
| Stale `__pycache__/` bytecode from old flat `.py` files causes import conflicts | Medium | Delete `src/tools/__pycache__/` entirely before running tests. Python regenerates bytecode for new package structure. |
| `pkgutil.iter_modules` returns both flat modules and packages, causing double-discovery during transition | Low | Phase 1 replaces `pkgutil.iter_modules` with `_discover_skills()` entirely — no transitional period needed. |
| Tests that import from `src.tools.<skill>` break because module is now a package | Low | Python resolves `import src.tools.application` correctly whether it's `application.py` or `application/__init__.py`. |
| Integration tests (executor, pipeline) depend on tools being registered correctly | Medium | Verified in Phase 3 smoke test — MCP server starts and tools are callable. |

---

## Rollback Plan

If Phase 1 causes issues, revert by:
1. Delete the 5 skill directories (`application/`, `vision/`, etc.)
2. Restore flat `.py` and `.toml` files from git: `git checkout src/tools/`
3. Restore `src/tools/__init__.py`: `git checkout src/tools/__init__.py`
4. Re-run tests: `python3 run_tests.py --unit`

The entire refactoring is a structural move — no logic changes in the skill source files themselves.

---

## Post-Phase-1: install_guides migration (executed)

The `install_guides` config was moved from `config.json` into `package_manager/config.toml`, following the same per-skill ownership pattern.

### Changes
| File | Action |
|------|--------|
| `package_manager/config.toml` | Added `[install_guides] directory = "install_guides"` section |
| `src/config.py` | `install_guides_dir()` now checks: 1) config.json override, 2) per-skill config.toml, 3) default. Removed `install_guides` from `DEFAULT_CONFIG`. |
| `config.json` | Removed `install_guides` section (per-skill config.toml is now the primary source) |
| `tests/test_config.py` | Added `test_install_guides_dir_reads_per_skill_config()` — verifies fallback when config.json has no `install_guides` |

### Verification
- All 11/11 unit tests pass (17 config checks)
- `install_guides_dir()` resolves from `package_manager/config.toml` when `config.json` has no override
- `_install_package('firefox')` writes to correct directory
- `config.json` still works as an override if present
