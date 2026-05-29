# GnomePilot — AGENTS.md

## Entry point & run
- `src/main.py` (`python -m src.main`) — CLI + TTS loop
- Config: `config.json` (models, skills toggle, debug, screenshots, install_guides, formatter)

## Architecture
Pipeline of 7 single-responsibility classes wired in `src/pipeline.py`:

```
Enrich (History) → Route (Router) → Build (History) → Execute (Executor) → Format (Formatter) → Store (History)
```

- 2 LangGraph `create_react_agent` subagents managed by `src/agents.py` (start, restart, shutdown)
- MCP tool server runs as a subprocess on stdio (`src/tools/server.py`)
- History is in-memory only — restart loses context
- Router: regex fast-path + LLM binary yes/no fallback

## Subagents

| Agent | Tools | Purpose |
|---|---|---|
| **general** | All except screen capture | Apps, packages, windows, web search, casual chat |
| **vision** | `tool_capture_screen` only | Screenshot + visual analysis |

All expert agents share the orchestrator LLM (`_general_llm`) — no extra VRAM cost. The vision agent uses its own model (configured via `models.vision` or `unified_model`).

### Routing flow
1. **Regex fast-path** on the original input:
   - Screen + action keywords → `["vision", "general"]` (chain)
   - Screen only → `["vision"]`
   - Action only → `["general"]`
2. **LLM binary yes/no fallback** (enriched with history context):
   - Returns one of: `general`, `vision`

## OpenCode Subagents (workflow delegation)

These are OpenCode subagents for the development workflow. Delegate to them
when the user's request matches their domain:

| Subagent | File | Delegate when the user... |
|---|---|---|
| **Python Expert** | `.opencode/agents/python-expert.md` | Writes, debugs, or reviews Python code; asks about imports, pip, async, type hints, or Python patterns |
| **OS/Linux Expert** | `.opencode/agents/os-expert.md` | Asks about Arch/CachyOS, pacman/yay, GNOME Wayland, DBus, systemd, shell scripts, or system config |
| **Security Expert** | `.opencode/agents/security-expert.md` | Requests security review, vulnerability assessment, secure coding patterns, or permission audit |
| **AI Integration Expert** | `.opencode/agents/ai-integration.md` | Writes/fixes tests, runs test suites, debugs pipeline failures, or asks about test strategy/coverage |

Each subagent has the project-specific context it needs baked into its prompt
(architecture, gotchas, tool patterns) so you don't need to repeat it.

## Change-cycle rule

After every change cycle (implementation, fix, refactor, or modification of any
kind), create or overwrite `EXECUTIVE_SUMMARY.md` at the project root with:

1. **Summary of executed changes** — every file created, modified, or deleted.
2. **Recommendations and opinions from each subagent** — simulate each
   subagent's perspective on the changes made. Include what each would praise,
   flag, or suggest doing differently.
3. **Manual test plan** — step-by-step instructions for a human to verify
   every change in this cycle. Include exact commands to run, what output to
   expect, and edge cases to check. Cover compile checks, unit tests,
   integration tests, and any manual smoke tests (e.g. "run the assistant and
   ask it to X").

The `EXECUTIVE_SUMMARY.md` serves as the running log of the session. Keep it
current — overwrite it each cycle rather than appending.

## Skill system
### Adding a skill
1. Create `src/tools/<name>/__init__.py` with `@tool()` decorators (import from `.._registry`)
2. Create `src/tools/<name>/manifest.toml` with `[skill]` section + `prompt_hint`
3. Create `src/tools/<name>/config.toml` with `[skill]\nenabled = true` (optional, defaults true)
4. Toggle via the skill's own `config.toml` — no need to edit `config.json`
5. `prompt_hint` auto-injects into `prompts/general.md` via `{tool_descriptions}` placeholder
6. `config.json` `"skills"` section acts as an optional override for backward compat

Skill folders are auto-discovered at startup — any directory under `src/tools/` containing
a `manifest.toml` is treated as a skill.  Shared helpers (`desktop_index.py`, `fuzzy_match.py`)
stay as flat files and are excluded from discovery naturally.

### @tool() returns a StructuredTool — NOT callable directly
Use `.invoke({"arg": val})` or `.func(arg)` in tests, not `tool_name(arg)`.

### Unavailable handler
Every skill `__init__.py` must export an `async def handler(input, config=None)`.
It returns `{"messages": [AIMessage(content="...")]}` when the skill is disabled.
The message is loaded from `manifest.toml` `[skill] unavailable_message`, falling
back to a hardcoded default in `__init__.py`.

When a skill becomes a standalone agent, wire it in `src/agents.py`:
```python
from src.tools.<name> import handler as _<name>_handler
# in start():
if not <name>_tools:
    self._<name>_agent = _<name>_handler
```
Currently only `vision` uses this pattern (the other 4 skills are sub-tools of
the general agent and don't need it — their absence is handled by the dynamic
`{tool_descriptions}` prompt).

## Tests
```sh
python3 run_tests.py              # all tests
python3 run_tests.py --unit       # no Ollama needed
python3 run_tests.py --integration # needs running Ollama
python3 run_tests.py --timeout 180
python3 run_tests.py --quiet
```
Integration tests: `{"test_agents", "test_executor", "test_pipeline", "test_close"}` — need Ollama running.

## Key gotchas
- **Screenshots**: Use `org.freedesktop.portal.Screenshot` (XDG Desktop Portal, Wayland). Shows permission dialog each time. Returns `file://` URI — strip with `.replace("file://", "")`.
- **Window Calls**: Two GNOME Shell extensions required at `~/.local/share/gnome-shell/extensions/`:
  - `window-calls-extended@hseliger.eu` — `List()`
  - `window-calls@domandoman.xyz` — `Close(id)`, `MoveToWorkspace(id, workspace)`
  - Both on `org.gnome.Shell`, path `/org/gnome/Shell/Extensions/Windows`
- **App launch**: Parses `Exec=` from `.desktop` files, uses `subprocess.Popen` with `DEVNULL` + `close_fds=True` — prevents PWA stdout from leaking into MCP JSON-RPC
- **Tool dedup**: Executor detects duplicate (name, args) calls and prepends a stop warning
- **Install guides**: `tool_install_package` does NOT install packages. It generates an MD file in `install_guides/` with pacman/yay commands the user can run manually. Configurable via `install_guides.directory`.
- **Recursion limit**: Configurable via `orchestrator.recursion_limit` (default 10). `GraphRecursionError` caught in Pipeline with user-friendly message
- **Ollama unload**: `ollama.generate(model=name, prompt="", keep_alive=0)` triggers `done_reason:"unload"` — frees VRAM
- **MCP subprocess env**: Whitelisted to `MCP_ENV_KEYS` in `src/agents.py`. GUI apps launched via `subprocess.Popen` inside the subprocess inherit this env — must include display vars (`WAYLAND_DISPLAY`, `DISPLAY`, `XDG_RUNTIME_DIR`). Before adding/removing keys, trace the full chain: MCP subprocess → tool function → Popen/DBus child. A unit test (`test_mcp_required_env_keys`) catches missing keys.
- **Prompts**: Editable Markdown in `prompts/` — `general.md`, `vision.md`, `router.md`. No code changes needed.
- **Formatter**: Strips emojis, zero-width chars, tool-call JSON artefacts, markdown fences via regex

## Dependencies (system)
```sh
sudo pacman -S python python-pip python-dbus python-gobject ollama dbus xdg-desktop-portal-gnome
ollama pull llama3.1:8b
ollama pull minicpm-v:8b
```

## Model sizing (fits 12 GB VRAM)
| Config | VRAM |
|--------|------|
| `unified_model: qwen3.5:2b` | 2.7 GB |
| llama3.1:8b + qwen3.5:2b | 8.3 GB |
| `unified_model: qwen3.5:9b` | 6.6 GB |

Use `unified_model` to avoid VRAM swapping between agents.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **GnomePilot** (1320 symbols, 2127 relationships, 28 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/GnomePilot/context` | Codebase overview, check index freshness |
| `gitnexus://repo/GnomePilot/clusters` | All functional areas |
| `gitnexus://repo/GnomePilot/processes` | All execution flows |
| `gitnexus://repo/GnomePilot/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
