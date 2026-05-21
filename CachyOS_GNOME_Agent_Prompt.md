# GnomePilot — CachyOS GNOME Local AI Assistant (Design Spec)

**Status:** Phase 4 in progress. Phases 1–3 complete and tested.

## Architecture Requirements

| Requirement | Planned | Implemented |
|-------------|---------|-------------|
| Language | Python 3.11+ | Python 3.14 |
| Orchestrator | LangChain / AutoGen | LangGraph `create_react_agent` with dual agents |
| Routing | LLM function-calling | Hybrid: regex (fast path) + LLM yes/no (ambiguous) + chaining support |
| Voice / TTS | Piper TTS + Whisper STT | Piper TTS integrated; STT stub (returns None, CLI fallback) |
| Vision | grim + llava:7b | XDG Desktop Portal (Wayland) + qwen3.5 via Ollama |
| LLM | llama3:8b-instruct | Configurable — qwen3.5:2b through qwen3.5:9b |
| Tooling | MCP (Model Context Protocol) | MCP stdio server with auto-discovery plugin system |
| Window Mgmt | GNOME Shell Extension DBus | Extension at `org.gnome.Shell.Extensions.Assistant` |

### Additional Features (beyond spec)

- **Desktop app index** — pre-built scored lookup of all .desktop files (275+ entries), supports PWAs with numeric IDs via Name= field matching
- **Chat history** — configurable multi-turn context (Human/AI message pairs)
- **Regex formatter** — strips emojis, invisible chars, leaked tool-call artifacts
- **Unified model mode** — single model for both agents to fit in < 12 GB VRAM
- **Context window** — configurable `num_ctx` (8192 default, up to 32768)
- **Recursion limit** — capped at 10 to prevent tool-call loops
- **Screenshot FIFO** — temp storage with configurable retention

---

## Phase 1: Core Orchestrator and Voice Foundation ✅

**Complete.** All tests pass.

- Python venv with LangChain/Ollama/LangGraph
- CLI input/output loop
- Piper TTS (`src/voice.py`) — synthesizes and plays via PipeWire
- STT stubbed out (returns None, falls back to text input)

---

## Phase 2: System Management Sub-Agents (MCP Integration) ✅

**Complete.** All tests pass.

- MCP client via `MultiServerMCPClient` + `langchain-mcp-adapters`
- Application agent: opens/closes via `.desktop` files + `Gio.DesktopAppInfo`
  - Searches `/usr/share/applications`, `~/.local/share/applications`, `~/Applications/`
  - PWA support via Name= field matching on numeric-ID desktop files
  - Fallback to `shlex.split(Exec=)` when GLib constructor fails
  - App name aliases (terminal → console, text editor → gedit)
- Package manager: `pacman -Ss` + `yay -Ss` (AUR), install via `pkexec pacman -S`
- `subprocess.os.environ` fix for MCP child process env filtering

---

## Phase 3: Spatial Awareness & Vision (Wayland/GNOME) ✅

**Complete.** All tests pass.

- Vision via XDG Desktop Portal (`org.freedesktop.portal.Screenshot`)
  - DBus mainloop in daemon thread, 20s timeout, permission dialog
  - Image resize (800px max) before base64 encode
  - Model unload before analysis for VRAM management
  - FIFO screenshot retention in `/tmp/os-assistant/screenshots`
- Window management via GNOME Shell Extension
  - ES module format (`export default class`) for GNOME 50
  - DBus under `org.gnome.Shell` bus name (not a separate name)
  - `MoveWindowToWorkspace(appName, workspaceIndex)` — 0-based indices

---

## Phase 4: Integration, Autonomy, and Refinement 🚧

### Task 4.1: Chaining & Sub-agent Routing ✅

**Complete.** Router tested 11/11 with qwen3.5:2b at 8192 ctx.

- Replaced hardcoded keyword matching with hybrid router
  - Regex fast-path for obvious screen/action patterns
  - LLM binary yes/no for ambiguous queries
  - Chain detection (screen + action) → runs agents sequentially
- Vision → General chain: vision result injected as context to general agent
- Chat history: remembers up to `chat_history_size` turns (configurable, default 10)
- Recursion limit: 10 (prevents tool-call loops)

### Task 4.2: Continuous Listening ❌

**Not yet implemented.**

- Planned: OpenWakeWord ("Hey Computer") + Whisper STT streaming
- Current: `listen()` stub returns None, CLI text input works

---

## Future Improvements

- [ ] OpenWakeWord/Whisper continuous listening loop
- [ ] Volume/mute TTS control
- [ ] Screen region selection for vision (not just full screen)
- [ ] Window list/close-by-name via GNOME Shell Extension
- [ ] Browser tab management via keyboard automation
- [ ] System monitor (CPU, RAM, temp) via MCP tools
- [ ] Notification management
- [ ] File management MCP tools
