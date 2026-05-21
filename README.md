# GnomePilot — CachyOS / GNOME Local AI Assistant

A fully local, voice-responsive OS assistant for CachyOS (Arch Linux) with
GNOME Wayland. Uses **Ollama** LLMs, **Piper TTS** for speech, **MCP**
for modular tooling, **LangGraph** subagents for specialized behavior,
and a **GNOME Shell Extension** for window management.

Fits within 12 GB VRAM, works down to a single 2.7 GB model (qwen3.5:2b).

## Architecture

```
User input → Hybrid Router (regex + LLM yes/no) → Subagent(s)
                                                    │
                                    ┌───────────────┴───────────────┐
                                    ▼                               ▼
                            General Agent                      Vision Agent
                         (apps, packages,                  (screenshot tool only)
                          windows, chat)
                                    │                               │
                                    ▼                               ▼
                            MCP Tool Server                  MCP Tool Server
                         ┌────────┼────────┐              ┌────┴────┐
                      apps    packages   windows       screenshot
```

### Agents

| Agent | Tools | Model | Description |
|-------|-------|-------|-------------|
| **General** | open/close apps, search/install packages, move windows | orchestrator model | Handles all non-vision tasks and casual chat |
| **Vision** | capture & analyze screen | vision model | Takes screenshot via XDG Desktop Portal, describes via Ollama VLM |

### Routing

Hybrid approach — no hardcoded if/else for most cases:

1. **Regex** catches obvious patterns instantly (screen/action keywords)
2. **LLM yes/no** handles ambiguous queries — a single binary question
   even a 2B model answers reliably
3. Screen + action → **chain mode**: vision runs first, its result is fed
   as context to the general agent

### Chaining

When the user asks something like *"Look at my screen and open that app"*:

1. Router detects both screen + action words → `["vision", "general"]`
2. Vision agent captures & analyzes the screen
3. General agent receives the vision context and performs the action

### Chat History

The assistant remembers previous conversation turns. Configurable
via `chat_history_size` (default 10, 0 = disabled). History is
injected as native (Human, AI) message pairs — the LLM sees
the full conversation naturally.

### Model Management

- Both agents default to separate models (e.g. llama3.1:8b + qwen3.5:2b)
- Set `unified_model` to force one model for both agents (eliminates VRAM
  swapping — essential with < 12 GB VRAM)
- Context window configurable via `num_ctx` (default 8192, qwen supports 32768)
- Vision agent auto-resizes screenshots (800px max) to reduce VRAM

## Directory Structure

```
GnomePilot/
├── config.json                  # All configuration
├── prompts/
│   ├── general.md               # General agent system prompt
│   ├── vision.md                # Vision agent system prompt
│   └── router.md                # Router classification prompt
├── src/
│   ├── config.py                # Config reader helpers
│   ├── orchestrator.py          # LangGraph subagent architecture
│   ├── main.py                  # CLI + TTS entry point
│   ├── voice.py                 # Piper TTS (speak) + STT stub (listen)
│   └── tools/
│       ├── __init__.py          # Auto-discovery plugin loader
│       ├── server.py            # MCP stdio server
│       ├── application.py       # Open/close desktop apps + PWA support
│       ├── package_manager.py   # Search/install via pacman + AUR (yay)
│       ├── vision.py            # Screenshot capture + Ollama vision analysis
│       └── window_manager.py    # Move windows via GNOME Shell Extension DBus
├── voices/                      # Piper voice model (.onnx.json)
├── test_phase1.py               # Phase 1 review gate
├── test_phase2.py               # Phase 2 review gate
├── test_phase3.py               # Phase 3 review gate
├── requirements.txt             # Python dependencies
├── setup.sh                     # Full installer
├── CachyOS_GNOME_Agent_Prompt.md  # Original design spec
└── README.md
```

### GNOME Shell Extension

Installed separately at `~/.local/share/gnome-shell/extensions/os-assistant@cachyos/`:

| File | Purpose |
|------|---------|
| `metadata.json` | Extension metadata (shell-version: "50") |
| `extension.js` | ES module exporting `MoveWindowToWorkspace(appName, workspaceIndex)` via DBus |

## Configuration

All tunables in `config.json`:

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
  }
}
```

| Key | Type | Default | Purpose |
|-----|------|---------|---------|
| `models.orchestrator` | string | `llama3.1:8b` | Model for general agent |
| `models.vision` | string | `qwen3.5:4b` | Model for vision agent |
| `unified_model` | string\|null | `null` | Single model for both agents (null = separate) |
| `orchestrator.temperature` | float | `0` | LLM temperature |
| `orchestrator.num_ctx` | int | `8192` | Context window size (Ollama `num_ctx`) |
| `orchestrator.chat_history_size` | int | `10` | Conversation turns to remember (0 = disabled) |
| `screenshots.directory` | string | `/tmp/os-assistant/screenshots` | Screenshot storage |
| `screenshots.max_retention` | int | `10` | Max screenshots (FIFO) |
| `screenshots.unload_before_analysis` | bool | `true` | Unload other models before vision |
| `formatter.enabled` | bool | `true` | Enable regex response formatter |

### Model Size Reference

| Model | Size | Best for |
|-------|------|----------|
| `qwen3.5:2b` | 2.7 GB | Minimal — everything on one model |
| `qwen3.5:4b` | 3.4 GB | Balanced — fits alongside llama3.1:8b |
| `qwen3.5:9b` | 6.6 GB | Recommended — much better routing & vision |
| `llama3.1:8b` | 4.9 GB | Strong tool calling |

### Quick Configs

```json
// Tiny setup (2.7 GB total — everything on qwen3.5:2b)
{ "unified_model": "qwen3.5:2b" }

// Balanced setup (8.3 GB total — llama3.1:8b + qwen3.5:2b)
{ "models": { "orchestrator": "llama3.1:8b", "vision": "qwen3.5:2b" } }

// High quality (12 GB — qwen3.5:9b for everything)
{ "unified_model": "qwen3.5:9b" }
```

## Prompts

Edit agent behavior without code changes — `prompts/*.md`:

| File | Controls |
|------|----------|
| `prompts/general.md` | How the assistant opens apps, installs packages, moves windows, chats |
| `prompts/vision.md` | How screen descriptions are worded (no file paths, natural tone) |
| `prompts/router.md` | Binary classification prompt for ambiguous routing |

## Formatter

Regex-based post-processor strips:
- Emojis and Unicode symbols
- Zero-width and invisible characters
- Leaked MCP tool-call JSON artifacts
- ` ```json ``` ` code fences

No LLM overhead — pure regex. Enable/disable via `formatter.enabled`.

## Requirements

### System Packages (Arch / CachyOS)

| Package | Purpose |
|---------|---------|
| `python` (>=3.11) | Runtime |
| `python-pip` | Package manager |
| `python-dbus` | DBus bindings |
| `python-gobject` | GObject (Gio) |
| `ollama` | LLM server |
| `base-devel` | Build tools |
| `xdg-desktop-portal-gnome` | Screenshot Wayland |
| `gnome-shell` | Extension runtime |

### Python Packages (pip, in .venv)

| Package | Purpose |
|---------|---------|
| `langchain` + `langchain-ollama` | LLM orchestration |
| `langchain-mcp-adapters` | MCP tool adapter |
| `langgraph` | Subagent graphs |
| `mcp` | MCP SDK |
| `piper-tts` | Text-to-speech |
| `ollama` | Python Ollama client |
| `Pillow` | Image resize |
| `PyGObject` | GLib bindings |
| `dbus-python` | Python DBus |

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

# 6. GNOME Shell Extension
# Copy the extension directory to:
#   ~/.local/share/gnome-shell/extensions/os-assistant@cachyos/
# Log out and back in to activate.
```

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

You: Open YouTube
Assistant: YouTube is now open!

You: What do you see on my screen and open that app
Assistant: [vision analysis] [opens the app from vision context]
```

## Testing

Phase review gates:

```bash
source .venv/bin/activate

python test_phase1.py   # Core orchestrator + TTS
python test_phase2.py   # App open/close + package install
python test_phase3.py   # Vision analysis + window management
```

## License

GNU GPLv3
