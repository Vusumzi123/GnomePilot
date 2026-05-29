"""Skill: Screen capture and visual analysis.

Uses XDG Desktop Portal for Wayland screenshots and Ollama vision models
for image description.

Auto-discovered via @tool() decorator — no manual wiring needed.
"""

import base64
import os
import random
import shutil
import string
import threading
import time
from pathlib import Path

import dbus
import ollama
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
from PIL import Image

from src.config import get_model, screenshot_dir, screenshot_retention, unload_before_analysis
from .._registry import tool

import tomllib
from langchain_core.messages import AIMessage

_HERE = Path(__file__).parent
_UNAVAILABLE_MSG = "I cannot see your screen right now — the vision/screenshot capability is not enabled."

_try_manifest = _HERE / "manifest.toml"
if _try_manifest.exists():
    try:
        _UNAVAILABLE_MSG = tomllib.loads(_try_manifest.read_text()).get(
            "skill", {}).get("unavailable_message", _UNAVAILABLE_MSG)
    except Exception:
        pass


async def handler(input, config=None):
    """Returned when the skill is disabled — provides a clear unavailable message."""
    return {"messages": [AIMessage(content=_UNAVAILABLE_MSG)]}


SCREENSHOT_TIMEOUT = 20.0


def _vision_model() -> str:
    return get_model("vision", "minicpm-v:8b")


def _take_screenshot(timeout: float = SCREENSHOT_TIMEOUT) -> str | None:
    """Capture the screen via XDG Desktop Portal (Wayland).

    Spawns a DBus thread that calls org.freedesktop.portal.Screenshot, waits
    for the user to accept the permission dialog, and returns the file path.
    Returns None on denial or timeout.
    """
    result: dict = {}
    done = threading.Event()

    def _run() -> None:
        DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        portal = bus.get_object(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
        )
        iface = dbus.Interface(portal, "org.freedesktop.portal.Screenshot")

        token = "os_" + "".join(random.choices(string.ascii_lowercase, k=8))
        opts = dbus.Dictionary({"handle_token": token}, signature="sv")
        handle = iface.Screenshot("", opts)

        loop = GLib.MainLoop()

        def on_response(response: int, results: dbus.Dictionary) -> None:
            if response == 0:
                uri = str(results.get("uri", ""))
                result["path"] = uri.replace("file://", "")
            loop.quit()

        bus.add_signal_receiver(
            on_response,
            "Response",
            "org.freedesktop.portal.Request",
            "org.freedesktop.portal.Desktop",
            handle,
        )

        source = GLib.timeout_add(int(timeout * 1000), loop.quit)
        loop.run()
        GLib.source_remove(source)

        done.set()

    thread = threading.Thread(target=_run, daemon=True, name="screenshot-portal")
    thread.start()
    done.wait(timeout + 2)
    return result.get("path")


def _resize_image(path: str, max_dim: int = 800) -> str:
    """Shrink image so longest side <= max_dim pixels, reducing VRAM footprint.
    Returns the resized path (or original if already small enough).
    """
    img = Image.open(path)
    if max(img.size) <= max_dim:
        return path
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    resized = path.replace(".png", "_small.png")
    img.save(resized, "PNG")
    return resized


def _analyze_image(image_path: str) -> str:
    """Send a resized base64-encoded image to the vision model for description.
    Cleans up the temporary resized copy after analysis.
    """
    small_path = _resize_image(image_path)
    data = base64.b64encode(Path(small_path).read_bytes()).decode()
    response = ollama.chat(
        model=_vision_model(),
        messages=[
            {
                "role": "user",
                "content": "Describe what is on this screen in 1-2 concise sentences.",
                "images": [data],
            }
        ],
        keep_alive=0 if unload_before_analysis() else None,
    )
    # Clean up resized file if it was created
    if small_path != image_path:
        Path(small_path).unlink(missing_ok=True)
    return response["message"]["content"]


def _unload_other_models() -> None:
    """Free VRAM by unloading all models except the vision model.
    Skipped when unload_before_analysis is false (both models fit in VRAM).
    """
    if not unload_before_analysis():
        return
    try:
        running = ollama.ps()
        for m in running.models:
            name = m.name or m.model
            if name and _vision_model() not in name:
                ollama.generate(model=name, prompt="", keep_alive=0)
    except Exception:
        pass


def _enforce_retention(directory: Path, max_files: int) -> None:
    """Delete oldest screenshots when count exceeds max_files (FIFO rotation)."""
    try:
        pngs = sorted(directory.glob("*.png"), key=lambda p: p.stat().st_mtime)
        while len(pngs) > max_files:
            old = pngs.pop(0)
            old.unlink(missing_ok=True)
    except Exception:
        pass


def _capture_and_analyze() -> str:
    """Orchestrate the full screenshot pipeline: capture, store, analyze.

    1. Take screenshot via portal
    2. Copy to temp store dir, clean up portal temp file
    3. Enforce FIFO retention
    4. Unload non-vision models from VRAM
    5. Run vision analysis and return the description
    """
    portal_path = _take_screenshot()
    if portal_path is None:
        return "Could not take a screenshot. The user may have denied the permission dialog, or the request timed out."

    store_dir = screenshot_dir()
    store_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d-%H%M%S")
    local_path = str(store_dir / f"shot-{ts}.png")
    shutil.copy2(portal_path, local_path)
    os.remove(portal_path)

    _enforce_retention(store_dir, screenshot_retention())

    try:
        _unload_other_models()
        description = _analyze_image(local_path)
        return description
    except Exception as e:
        return f"Analysis failed: {e}"



@tool()
def tool_capture_screen() -> str:
    """Capture the current screen and describe what is visible.

    Takes a screenshot via the system's screenshot portal (may show a
    permission dialog) and analyzes the image using a local vision model
    to describe what is currently on screen.
    """
    return _capture_and_analyze()
