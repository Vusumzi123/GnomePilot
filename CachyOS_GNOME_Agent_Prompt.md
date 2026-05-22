# GnomePilot — CachyOS GNOME Local AI Assistant (Design Spec)

**Status:** Phase 4 complete. Pipeline architecture deployed.
Skill auto-discovery (Steps 2–7) in progress.

## Architecture Requirements

| Requirement | Planned | Implemented |
|---|---|---|
| Language | Python 3.11+ | Python 3.14 |
| Orchestrator | LangChain / AutoGen | **Pipeline (Chain of Responsibility)** — 7 single-responsibility classes: `Router`, `Executor`, `History`, `Formatter`, `Extractor`, `Agents`, `Pipeline` |
| Routing | LLM function-calling | Hybrid: regex fast-path + LLM yes/no + history enrichment for context-aware routing |
| Voice / TTS | Piper TTS + Whisper STT | Piper TTS integrated; STT stub (returns None, CLI fallback) |
| Vision | grim + llava:7b | XDG Desktop Portal (Wayland) + qwen3.5 via Ollama |
| LLM | llama3:8b-instruct | Configurable — qwen3.5:2b through qwen3.5:9b |
| Tooling | MCP (Model Context Protocol) | MCP stdio server with auto-discovery + deferred `@tool()` registry |
| Window Mgmt | GNOME Shell Extension DBus | `MoveWindowToWorkspace` + `List()`/`Close(id)` via Window Calls extensions |

### Additional Features (beyond original spec)

- **Pipeline architecture** — Router, History, Executor, Formatter, Extractor, Agents each in own file
- **Fuzzy match** — reusable `score()`, `best()`, `ranked()` string matcher (100/90/70/50 scoring)
- **DBus window close** — Window Calls Extended `List()` + `Close()` with fuzzy title matching
- **Desktop app index** — pre-built `.desktop` file index with scored lookup (275+ entries), PWA support
- **Chat history** — configurable multi-turn context with `enrich_for_routing()` context injection
- **Regex formatter** — strips emojis, invisible chars, leaked tool-call artifacts
- **Unified model mode** — single model for both agents to fit in < 12 GB VRAM
- **Context window** — configurable `num_ctx` (8192 default, up to 32768)
- **Tool call deduplication** — detects LLM retry loops, warns user
- **PWA stdout fix** — app launches redirect stdio to DEVNULL (prevents MCP JSON-RPC corruption)
- **Skill auto-discovery** — adding a skill = 2 files (`.py` + `.toml`), zero boilerplate
- **Skill manifests** — `.toml` files with `prompt_hint` auto-populate agent system prompt
- **Configurable skills** — toggle individual tool modules via `config.json`
- **Dynamic test runner** — `run_tests.py` auto-discovers all `test_*.py` suites
- **Loguru debug logging** — stderr + file sinks with rotation/retention

---

## Phase 1: Core Orchestrator and Voice Foundation ✅

**Complete.** All tests pass.

- Python venv with LangChain/Ollama/LangGraph
- CLI input/output loop
- Piper TTS (`src/voice.py`) — synthesizes and plays via PipeWire
- STT stubbed out (returns None, falls back to text input)
- **Refactored:** `Orchestrator` replaced by Pipeline (7 domain classes)

---

## Phase 2: System Management Sub-Agents (MCP Integration) ✅

**Complete.** All tests pass.

- MCP client via `MultiServerMCPClient` + `langchain-mcp-adapters`
- Application agent: open/close via `.desktop` files + `Gio.DesktopAppInfo`
  - Searches `/usr/share/applications`, `~/.local/share/applications`, `~/Applications/`
  - PWA support via `Name=` field matching on numeric-ID desktop files
  - Fallback to `shlex.split(Exec=)` when GLib constructor fails
  - App launch redirects stdio to DEVNULL (PWA stdout leak fix)
  - App close via **DBus Window Calls** — `List()` + fuzzy match + `Close(id)`
- Package manager: `pacman -Ss` + `yay -Ss` (AUR), install via `pkexec pacman -S`

---

## Phase 3: Spatial Awareness & Vision (Wayland/GNOME) ✅

**Complete.** All tests pass.

- Vision via XDG Desktop Portal (`org.freedesktop.portal.Screenshot`)
  - DBus mainloop in daemon thread, 20s timeout, permission dialog
  - Image resize (800px max) before base64 encode
  - Model unload before analysis for VRAM management
- Window management via GNOME Shell Extension
  - ES module format (`export default class`) for GNOME 50
  - `MoveWindowToWorkspace(appName, workspaceIndex)` — 0-based indices

---

## Phase 4: Integration, Autonomy, and Refinement ✅

**Complete.** Pipeline architecture deployed.

### Task 4.1: Chaining & Sub-agent Routing ✅

- Pipeline: `Router` → `Executor` → `History` → `Formatter` → `Extractor`
- Hybrid router: regex fast-path + LLM binary classifier + history enrichment
- Chain detection: screen + action → `["vision", "general"]`
- Vision → General context injection
- Chat history: configurable turns, `HumanMessage/AIMessage` pairs
- Context-aware routing enrichment (`[History: ...]` prefix)
- Tool call deduplication — detects and warns on LLM retry loops
- Recursion limit: 5 (prevents infinite loops)

### Task 4.2: Continuous Listening ❌

**Not yet implemented.**

- Planned: OpenWakeWord ("Hey Computer") + Whisper STT streaming
- Current: `listen()` stub returns None, CLI text input works

---

## Future Improvements

- [ ] Step 2–7 of `PLAN_SKILL_AUTO_DISCOVERY.md` (convert skills to `@tool()` + manifests)
- [ ] OpenWakeWord/Whisper continuous listening loop
- [ ] HTTP API backend (FastAPI) — Chat, Config, Log endpoints
- [ ] Web UI (Svelte or htmx) served as static files
- [ ] Volume/mute TTS control
- [ ] Screen region selection for vision (not just full screen)
- [ ] Window list/close-by-name via GNOME Shell Extension
- [ ] Browser tab management via keyboard automation
- [ ] System monitor (CPU, RAM, temp) via MCP tools
- [ ] Notification management
- [ ] File management MCP tools
