# GnomePilot — CachyOS / GNOME Local AI Assistant

A fully local, voice-responsive OS assistant for CachyOS (Arch Linux) with
GNOME Wayland. Uses **Ollama** LLMs, **Piper TTS** for speech, **MCP**
for modular tooling, **LangGraph** subagents for specialized behavior,
and **GNOME Shell Extensions** for window management.

Fits within 12 GB VRAM, works down to a single 2.7 GB model (qwen3.5:2b).

## Architecture

```
main.py ──► Pipeline ──► Enrich ──► Route ──► Build ──► Execute ──► Format ──► Store
               │            │          │         │          │           │          │
               │        (History)   (Router)  (History)  (Executor)  (Formatter) (History)
               │
               └──► Agents (Ollama ×3 + MCP subprocess + LangGraph agents)
                         │
                         └──► MCP Server (auto-discovered skills, config-togglable)
```

### Pipeline stages (Chain of Responsibility)

| Stage | Class | File | What it does |
|---|---|---|---|
| Enrich | `History` | `src/history.py` | Prepends recent chat context for routing |
| Route | `Router` | `src/router.py` | Hybrid regex + LLM yes/no classifier |
| Build | `History` | `src/history.py` | Constructs LangChain message list with history |
| Execute | `Executor` | `src/executor.py` | Runs agents in sequence, handles chaining |
| Format | `Formatter` | `src/formatter.py` | Regex cleanup of LLM output |
| Store | `History` | `src/history.py` | Appends turn to conversation memory |

### Agents

| Agent | Tools | Model | Description |
|---|---|---|---|
| **General** | open/close apps, search/install packages, move windows | orchestrator model | Handles non-vision tasks and casual chat |
| **Vision** | capture & analyze screen | vision model | Screenshot via XDG Desktop Portal, analysis via Ollama VLM |

### Routing

Three-tier hybrid approach:

1. **History enrichment** — recent user queries prepended as `[History: ...]` prefix,
   letting the router resolve anaphora ("describe it again" after a vision turn).
2. **Regex fast-path** — catches obvious screen/action keywords in the **original**
   input only (avoids false positives from history contamination).
3. **LLM fallback** — binary yes/no question for ambiguous queries, receives the
   enriched input with history context. Reliable even on 2B models.

Screen + action → **chain mode**: vision runs first, its output injected as
context to the general agent.

### Chaining

When the user says *"Look at my screen and open that app"*:

1. Router detects screen + action keywords → `["vision", "general"]`
2. Vision agent captures and describes the screen
3. General agent receives `[vision analysis]` as context and performs the action

### Tool call deduplication

The `Executor` detects when the LLM calls the same tool with the same arguments
more than once (looping) and prepends a warning to the response. Combined with
a recursion limit of 5, this prevents infinite retry loops.

### Model Management

- Both agents default to separate models (e.g. llama3.1:8b + qwen3.5:2b)
- Set `unified_model` to force one model for both agents (eliminates VRAM swapping)
- Context window configurable via `num_ctx` (default 8192, qwen supports 32768)
- Vision agent auto-resizes screenshots (800px max) to reduce VRAM
- `Agents.restart()` re-spawns the MCP subprocess for live config changes

---

## Directory Structure

```
GnomePilot/
├── config.json                  # All configuration
├── prompts/
│   ├── general.md               # General agent system prompt
│   ├── vision.md                # Vision agent system prompt
│   └── router.md                # Router classification prompt (2 lines)
├── src/
│   ├── agents.py                # LLM + MCP + LangGraph agent lifecycle
│   ├── config.py                # Config reader helpers
│   ├── debug.py                 # Loguru setup + DebugCallbackHandler
│   ├── executor.py              # Agent chain runner with deduplication
│   ├── extractor.py             # Response text + tool call extraction
│   ├── formatter.py             # Regex response cleanup
│   ├── history.py               # Chat turns, message building, routing enrichment
│   ├── main.py                  # CLI + TTS entry point
│   ├── pipeline.py              # Pipeline coordinator + Context dataclass
│   ├── router.py                # Hybrid regex + LLM routing
│   ├── voice.py                 # Piper TTS (speak) + STT stub (listen)
│   └── tools/
│       ├── __init__.py          # Auto-discovery skill loader
│       ├── _registry.py         # Deferred @tool() decorator
│       ├── server.py            # MCP stdio server + reload_tools()
│       ├── application.py       # Open/close desktop apps
│       ├── desktop_index.py     # .desktop file scanner + resolve
│       ├── fuzzy_match.py       # Generic string scorer (reusable)
│       ├── package_manager.py   # Search/install via pacman + AUR (yay)
│       ├── vision.py            # Screenshot capture + Ollama analysis
│       └── window_manager.py    # Move windows via GNOME Shell Extension
├── test_agents.py               # Agent lifecycle tests
├── test_close.py                # DBus window close tests
├── test_executor.py             # Executor chain + dedup tests
├── test_extractor.py            # Response extraction tests
├── test_formatter.py            # Formatter regex tests
├── test_history.py              # History management tests
├── test_pipeline.py             # Full pipeline integration tests
├── test_router.py               # Router regex + LLM tests
├── test_skill_registry.py       # Deferred @tool() registry tests
├── run_tests.py                 # Dynamic test runner
├── requirements.txt             # Python dependencies
├── setup.sh                     # Full installer
├── PLAN_REFACTOR_PIPELINE.md    # Pipeline architecture design
├── PLAN_CLOSE_WINDOW_DBUS.md    # DBus window close design
├── PLAN_SKILL_AUTO_DISCOVERY.md # Auto-discovery skills design
└── README.md
```

### GNOME Shell Extensions

Installed separately at `~/.local/share/gnome-shell/extensions/`:

| Extension | UUID | Purpose |
|---|---|---|
| Window Calls Extended | `window-calls-extended@hseliger.eu` | `List()` — enumerate open windows |
| Window Calls | `window-calls@domandoman.xyz` | `Close(id)`, `MoveToWorkspace(id, workspace)` |

---

## Configuration

### Full reference

```json
{
  "models": {
    "orchestrator": "llama3.1:8b",
    "vision": "qwen3.5:2b"
  },
  "unified_model": "qwen3.5:2b",
  "orchestrator": {
    "temperature": 0,
    "num_ctx": 8192,
    "chat_history_size": 10
  },
  "screenshots": {
    "directory": "/tmp/os-assistant/screenshots",
    "max_retention": 10,
    "unload_before_analysis": false
  },
  "formatter": {
    "enabled": true
  },
  "debug": {
    "enabled": false,
    "verbose": false,
    "log_dir": "logs",
    "retention_days": 7,
    "rotation": "10 MB"
  },
  "skills": {
    "package_manager": true
  }
}
```

| Key | Type | Default | Purpose |
|---|---|---|---|
| `models.orchestrator` | string | `llama3.1:8b` | Model for general agent |
| `models.vision` | string | `qwen3.5:4b` | Model for vision agent |
| `unified_model` | string\|null | `null` | Single model for both agents |
| `orchestrator.temperature` | float | `0` | LLM temperature |
| `orchestrator.num_ctx` | int | `8192` | Context window size (`ollama num_ctx`) |
| `orchestrator.chat_history_size` | int | `10` | Conversation turns to remember (0 = disabled) |
| `orchestrator.recursion_limit` | int | `10` | Max LLM-tool steps per agent call |
| `screenshots.directory` | string | `/tmp/os-assistant/screenshots` | Screenshot storage |
| `screenshots.max_retention` | int | `10` | Max screenshots (FIFO) |
| `screenshots.unload_before_analysis` | bool | `true` | Unload other models before vision |
| `formatter.enabled` | bool | `true` | Enable regex response formatter |
| `debug.enabled` | bool | `false` | Master toggle for debug logging |
| `debug.verbose` | bool | `false` | Full LLM prompt dumps when true |
| `debug.log_dir` | string | `"logs"` | Persistent log directory |
| `debug.retention_days` | int | `7` | Log file retention |
| `debug.rotation` | string | `"10 MB"` | Log file rotation size |
| `skills.<name>` | bool | `true` | Enable/disable a skill module |

### Skills

Each skill module in `src/tools/` can be toggled on/off:

```json
{
  "skills": {
    "application": true,
    "package_manager": false,
    "window_manager": true,
    "vision": true
  }
}
```

| Skill | Module | Tools provided |
|---|---|---|
| `application` | `application.py` | Open/close desktop apps (DBus window close with fuzzy matching) |
| `package_manager` | `package_manager.py` | Search (pacman/AUR) + install packages |
| `window_manager` | `window_manager.py` | Move windows between workspaces |
| `vision` | `vision.py` | Screenshot capture + visual analysis |

Skills default to enabled. Only add entries to **disable** a skill.

### Model Size Reference

| Model | Size | Best for |
|---|---|---|
| `qwen3.5:2b` | 2.7 GB | Minimal — everything on one model |
| `qwen3.5:4b` | 3.4 GB | Balanced — fits alongside llama3.1:8b |
| `qwen3.5:9b` | 6.6 GB | Recommended — better routing & vision |
| `llama3.1:8b` | 4.9 GB | Strong tool calling |

### Quick Configs

```json
// Tiny — 2.7 GB, everything on qwen3.5:2b
{ "unified_model": "qwen3.5:2b" }

// Balanced — 8.3 GB, llama3.1:8b + qwen3.5:2b
{ "models": { "orchestrator": "llama3.1:8b", "vision": "qwen3.5:2b" } }

// High quality — 12 GB, qwen3.5:9b for everything
{ "unified_model": "qwen3.5:9b" }
```

---

## Prompts

Edit agent behavior without code changes — `prompts/*.md`:

| File | Controls |
|---|---|
| `prompts/general.md` | How the assistant opens apps, installs packages, moves windows, chats |
| `prompts/vision.md` | How screen descriptions are worded (no file paths, natural tone) |
| `prompts/router.md` | Binary yes/no classifier (2 lines) |

---

## Key Features

### App Launch

Finds `.desktop` files via scored fuzzy matching (exact=100, prefix=90,
whole-word=70, substring=50). Supports PWAs with numeric filenames by
reading the `Name=` field. Launches via `Popen` with redirected stdio
to prevent PWA output from corrupting the MCP JSON-RPC channel.

### Window Close (DBus)

Uses Window Calls Extended to list all open windows, fuzzy-matches the
best title, and closes via DBus. No `pkill`/`killall` — works with
Electron/PWA apps whose process names don't match the app name.

If no match is found, the full window list is returned so the user
or assistant can pick the right one.

### Chat History

Remembers up to `chat_history_size` turns. History is injected as
`(Human, AI)` message pairs into the general agent's context.
Vision agent receives no history (isolated context per turn).

Context-aware routing enrichment prepends recent user queries as a
`[History: ...]` prefix — the router can disambiguate "describe it again"
after a vision turn without leaking history into the regex path.

### Formatter

Regex-based post-processor strips:
- Emojis and Unicode symbols
- Zero-width and invisible characters
- Leaked MCP tool-call JSON artifacts
- Markdown code fences

No LLM overhead — pure regex.

### Debug Logging (Loguru)

Two sinks:
- **stderr** — colorized, level matches `debug.verbose` (INFO or DEBUG)
- **File** — `logs/opencode_YYYY-MM-DD.log`, always DEBUG, rotates by size,
  retains N days, gzips old files

Full LLM prompt dumps visible when `debug.verbose: true`.

### Fuzzy Matching (reusable)

`src/tools/fuzzy_match.py` provides `score()`, `best()`, `ranked()` —
a general-purpose string matcher used by both app resolution and window close.
Scores exact/prefix/whole-word/substring matches.

---

## Requirements

### System Packages (Arch / CachyOS)

| Package | Purpose |
|---|---|
| `python` (>=3.11) | Runtime |
| `python-pip` | Package manager |
| `python-dbus` | DBus bindings |
| `python-gobject` | GObject (Gio) |
| `ollama` | LLM server |
| `base-devel` | Build tools |
| `xdg-desktop-portal-gnome` | Screenshot Wayland |
| `gnome-shell` | Extension runtime |

### GNOME Shell Extensions

| Extension | EGO link | Purpose |
|---|---|---|
| Window Calls | `window-calls@domandoman.xyz` | List, close, and move windows between workspaces |

### Python Packages (pip, in .venv)

| Package | Purpose |
|---|---|
| `langchain` + `langchain-ollama` | LLM orchestration |
| `langchain-mcp-adapters` | MCP tool adapter |
| `langgraph` | Subagent graphs |
| `mcp` | MCP SDK |
| `piper-tts` | Text-to-speech |
| `ollama` | Python Ollama client |
| `loguru` | Debug logging |
| `Pillow` | Image resize |

---

## Installation

```bash
chmod +x setup.sh
./setup.sh
```

Or manually:

```bash
# 1. System packages
sudo pacman -S --needed python python-pip python-dbus python-gobject \
  ollama base-devel xdg-desktop-portal-gnome

# 2. Start Ollama
sudo systemctl enable --now ollama

# 3. Python venv
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# 4. Pull models
ollama pull qwen3.5:2b

# 5. Voice models (optional, for TTS)
mkdir -p voices
# Download Piper voice from https://huggingface.co/rhasspy/piper-voices

# 6. GNOME Shell Extensions
# Install from extensions.gnome.org:
#   - Window Calls
# Log out and back in to activate.
```

---

## Usage

```bash
source .venv/bin/activate
python -m src.main
```

Type queries or use voice input (STT stub — falls back to keyboard).
Type `exit` or `quit` to stop (Ctrl+C also works).

```
You: What is on my screen?
Assistant: I can see VS Code with a Python file open...

You: Open YouTube Music
Assistant: Opened YouTube Music.

You: Close YouTube Music
Assistant: Closed YouTube Music.

You: What do you see on my screen and open that app
Assistant: [vision analysis] [opens the app from vision context]
```

---

## Testing

### Dynamic test runner

```bash
source .venv/bin/activate

python run_tests.py                  # all 8 suites (unit + integration)
python run_tests.py --unit           # 4 unit suites, no Ollama, ~1s
python run_tests.py --integration    # 4 integration suites, needs Ollama
python run_tests.py --quiet          # summary only
python run_tests.py test_router     # single suite
```

### Test suites

| Suite | Type | What it tests |
|---|---|---|
| `test_extractor` | Unit | Response text + tool call extraction |
| `test_formatter` | Unit | Regex cleanup (emoji, fences, metadata) |
| `test_history` | Unit | Chat turns, message building, enrichment |
| `test_router` | Unit | Regex + mock LLM routing |
| `test_skill_registry` | Unit | Deferred @tool() decorator |
| `test_agents` | Integration | MCP start, agent creation, shutdown |
| `test_executor` | Integration | Agent chaining, tool call deduplication |
| `test_pipeline` | Integration | Full pipeline with real agents + chain |
| `test_close` | Integration | DBus window close with fuzzy matching |

---

## Design Documents

| File | Topic |
|---|---|
| `PLAN_REFACTOR_PIPELINE.md` | Pipeline architecture design (phases 1–4) |
| `PLAN_CLOSE_WINDOW_DBUS.md` | DBus window close with fuzzy matching |
| `PLAN_SKILL_AUTO_DISCOVERY.md` | Auto-discovery skills (deferred registry + manifests) |

---

## License

GNU GPLv3
