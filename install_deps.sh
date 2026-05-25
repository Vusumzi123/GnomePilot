#!/usr/bin/env bash
# GnomePilot — Python venv dependency installer
# Usage: chmod +x install_deps.sh && ./install_deps.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo "=== GnomePilot — venv dependency install ==="
echo ""

if [ ! -d "$VENV_DIR" ]; then
    echo ">>> Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo ">>> Using existing virtual environment at .venv/"
fi

source "$VENV_DIR/bin/activate"

echo ">>> Upgrading pip..."
pip install -U pip

echo ">>> Installing Python dependencies..."
pip install -r "$PROJECT_DIR/requirements.txt"

echo ""
echo "=== Done ==="
echo ""
echo "To run the assistant:"
echo "  source .venv/bin/activate"
echo "  python -m src.main"
