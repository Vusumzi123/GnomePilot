#!/usr/bin/env bash
# OS Assistant — Full dependency installer for CachyOS / Arch Linux
# Usage: chmod +x setup.sh && ./setup.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo "=== OS Assistant Setup ==="
echo ""

# ── 1. System packages ──────────────────────────────────────────────────
echo ">>> Installing system packages..."
sudo pacman -S --needed --noconfirm \
    python \
    python-pip \
    python-dbus \
    python-gobject \
    ollama \
    base-devel \
    dbus \
    xdg-desktop-portal-gnome

# ── 2. Enable / start Ollama ────────────────────────────────────────────
echo ">>> Enabling and starting ollama service..."
sudo systemctl enable --now ollama 2>/dev/null || true

# ── 3. Python virtual environment ───────────────────────────────────────
echo ">>> Creating Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    python -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install -U pip
pip install -r "$PROJECT_DIR/requirements.txt"

# ── 4. Pull Ollama models ───────────────────────────────────────────────
echo ">>> Pulling Ollama models (this may take a while)..."
ollama pull llama3.1:8b
ollama pull minicpm-v:8b

# ── 5. Piper voice models (optional) ────────────────────────────────────
echo ""
echo ">>> Piper voice models -- SKIPPED."
echo "    To install voices, download .onnx + .onnx.json files from:"
echo "    https://huggingface.co/rhasspy/piper-voices"
echo "    and place them in:  $PROJECT_DIR/voices/"
echo ""

# ── 6. GNOME Shell Extension ────────────────────────────────────────────
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/os-assistant@cachyos"
if [ -d "$PROJECT_DIR/os-assistant@cachyos" ]; then
    echo ">>> Installing GNOME Shell Extension..."
    mkdir -p "$EXT_DIR"
    cp -r "$PROJECT_DIR/os-assistant@cachyos/"* "$EXT_DIR/"
    echo "    Extension copied to $EXT_DIR"
    echo "    !!! Log out and back in to activate it. !!!"
else
    echo ">>> GNOME Shell Extension not bundled -- skipping."
    echo "    (Install manually from: src/gnome-shell-extension/ if applicable)"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "To run the assistant:"
echo "  source .venv/bin/activate"
echo "  python -m src.orchestrator"
echo ""
echo "Make sure Ollama is running:  systemctl status ollama"
