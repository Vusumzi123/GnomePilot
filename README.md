# OS Assistant — CachyOS / GNOME (GnomePilot)

A modular, configurable voice assistant for CachyOS (Arch Linux) with
GNOME Wayland. Uses **Ollama** LLMs locally, **Piper TTS** for speech,
**MCP** for modular tooling, **LangGraph** subagents for specialized
behavior, and a **GNOME Shell Extension** for window management.

## Architecture

```
User input → Keyword router → Subagent (LangGraph create_react_agent)
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            General Agent                      Vision Agent
          (shared model)                  (vision model or shared)
                    │                               │
                    ▼                               ▼
            MCP Tool Server                  MCP Tool Server
         ┌────────┼────────┐              ┌────┴────┐
      apps    packages  windows          screenshot
```

- **General Agent** — Handles applications, packages, window management,
  and general chat. Uses the orchestrator model by default.
- **Vision Agent** — Captures and analyzes the screen via XDG Desktop
  Portal + Ollama vision model. Has a distinct system prompt that
  prevents mentioning file paths or technical capture details.

### Routing

Simple keyword matching routes vision requests to the Vision Agent.
Everything else goes to the General Agent.

### Model Management

- Both agents default to separate models (e.g. llama3.1:8b + qwen3.5:2b)
- Set `unified_model` in config to force a single model for both agents
  (eliminates VRAM swapping overhead)
- The vision agent auto-unloads other models before analysis and resizes
  screenshots to reduce VRAM usage

## Directory Structure

```
OS assistant/
├── config.json              # Model selection, unified_model, temperature
├── prompts/
│   ├── general.md           # General agent personality / instructions
│   └── vision.md            # Vision agent personality / instructions
├── src/
│   ├── config.py            # Config + prompt file reader
│   ├── orchestrator.py      # LangGraph subagent architecture
│   ├── main.py              # CLI entry point
│   ├── voice.py             # Piper TTS integration
│   └── tools/
│       ├── __init__.py      # Auto-discovery (register pattern)
│       ├── server.py        # MCP stdio server entry point
│       ├── application.py   # tool_open_application / tool_close_application
│       ├── package_manager.py  # tool_search_packages / tool_install_package
│       ├── vision.py        # tool_capture_screen (screenshot + analysis)
│       └── window_manager.py   # tool_move_window_to_workspace (DBus → Extension)
├── voices/                  # Piper voice model files (.onnx + .json)
├── test_phase1.py           # Phase 1 review gate
├── test_phase2.py           # Phase 2 review gate
├── test_phase3.py           # Phase 3 review gate
├── requirements.txt         # Python package dependencies
├── setup.sh                 # Full installation script
└── README.md                # This file
```

GNOME Shell Extension (installed separately):
```
~/.local/share/gnome-shell/extensions/os-assistant@cachyos/
├── metadata.json
└── extension.js
```

## Configuration

All tunables live in `config.json`:

```json
{
  "models": {
    "orchestrator": "llama3.1:8b",
    "vision": "qwen3.5:9b"
  },
  "unified_model": null,
  "orchestrator": {
    "temperature": 0
  }
}
```

| Key | Purpose |
|-----|---------|
| `models.orchestrator` | Model for the General Agent (all non-vision tasks) |
| `models.vision` | Model for the Vision Agent (screen analysis) |
| `unified_model` | Set to a model name to force both agents to share one model. `null` = use separate models. |
| `orchestrator.temperature` | LLM temperature (0 = deterministic) |

### Subagent Prompts

Edit the behavior of each agent by modifying its markdown prompt file:

- `prompts/general.md` — Instructions for the general-purpose agent
- `prompts/vision.md` — Instructions for the screen analysis agent

Example vision prompt snippet:
```markdown
## Behavior
- NEVER mention file paths, screenshot filenames, or technical capture details
- Describe the content naturally like you're looking at the screen
```

## Requirements

### System Packages (Arch Linux / CachyOS)

| Package | Purpose |
|---------|---------|
| `python` (>=3.11) | Runtime |
| `python-pip` | Package manager |
| `python-dbus` | DBus bindings |
| `python-gobject` | GObject introspection (Gio) |
| `ollama` | LLM inference server |
| `base-devel` | Build tools for pip native modules |
| `dbus` | Message bus |
| `xdg-desktop-portal-gnome` | Screenshot portal (Wayland) |
| `gnome-shell` | Extension runtime |
| `imagemagick` | Image resizing (optional, PIL works too) |

### Python Packages (pip)

Installed in a venv (`$project/.venv`):

| Package | Version | Purpose |
|---------|---------|---------|
| `langchain` | >=1.0 | Orchestration framework |
| `langchain-ollama` | >=1.0 | Ollama integration |
| `langchain-mcp-adapters` | >=0.2 | MCP tool adapter |
| `langgraph` | >=1.0 | Subagent graph execution |
| `mcp` | >=1.0 | MCP SDK (stdio server) |
| `piper-tts` | >=1.4 | Text-to-speech |
| `ollama` | >=0.6 | Python Ollama client |
| `Pillow` | >=10.0 | Image resize before vision analysis |
| `PyGObject` | — | GObject Python bindings |
| `dbus-python` | — | Python DBus bindings |

### Ollama Models

| Model | Size | Purpose |
|-------|------|---------|
| `llama3.1:8b` | 4.9 GB | Core LLM (tool calling) |
| `qwen3.5:9b` | 6.6 GB | Recommended vision + general model |
| `minicpm-v:8b` | 5.5 GB | Lightweight vision alternative |
| Piper voices | ~300 MB | Voice models (download manually) |

## Installation

```bash
chmod +x setup.sh
./setup.sh
```

Or step by step:

```bash
# 1. System packages
sudo pacman -S --needed python python-pip python-dbus python-gobject \
  ollama base-devel xdg-desktop-portal-gnome imagemagick

# 2. Start Ollama
sudo systemctl enable --now ollama

# 3. Python venv
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# 4. Pull Ollama models
ollama pull llama3.1:8b
ollama pull qwen3.5:9b

# 5. Voice models (optional, for TTS)
mkdir -p voices
# Download from https://huggingface.co/rhasspy/piper-voices

# 6. GNOME Shell Extension
# Copy the extension directory to:
#   ~/.local/share/gnome-shell/extensions/os-assistant@cachyos/
# Then log out and back in to activate.
```

## Usage

```bash
source .venv/bin/activate
python -m src.main
```

### Quick model swaps

Edit `config.json` to change models without touching code:

```json
// Use qwen3.5:9b for everything (no VRAM swapping)
{ "unified_model": "qwen3.5:9b" }

// Try a smaller vision model
{ "models": { "vision": "minicpm-v:8b" } }

// Back to separate models
{ "unified_model": null, "models": { "orchestrator": "llama3.1:8b", "vision": "qwen3.5:9b" } }
```

### Customize agent behavior

Edit the prompt files under `prompts/`:

```bash
$EDITOR prompts/vision.md   # Change how the vision agent describes your screen
$EDITOR prompts/general.md  # Change how the general agent responds
```

## License

GNU GPLv3
