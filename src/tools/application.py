"""Skill: Application management (launch & close desktop apps).

Register with `register(mcp)` -- called automatically by the plugin loader.
"""

import subprocess
from pathlib import Path

from gi.repository import Gio

DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path.home() / ".local/share/applications",
]


def _find_desktop_file(app_name: str) -> Path | None:
    """Search /usr/share/applications and ~/.local/share/applications for a matching .desktop file.
    Matches if the search name is contained in or starts with the desktop file name (case-insensitive).
    """
    search_name = app_name.lower().replace(" ", "")
    for desktop_dir in DESKTOP_DIRS:
        if not desktop_dir.exists():
            continue
        for entry in desktop_dir.iterdir():
            if not entry.suffix == ".desktop":
                continue
            name = entry.stem.lower().replace(" ", "")
            if search_name in name or name.startswith(search_name):
                return entry
    return None


def _open_application(app_name: str) -> str:
    """Find a .desktop file for app_name and launch it via Gio.DesktopAppInfo."""
    desktop_file = _find_desktop_file(app_name)
    if desktop_file is None:
        return f"Could not find an application matching '{app_name}'."

    app_info = Gio.DesktopAppInfo.new_from_filename(str(desktop_file))
    if app_info is None:
        return f"Failed to load desktop file for '{app_name}'."

    launched = app_info.launch()
    if launched:
        return f"Successfully launched {app_name}."
    return f"Failed to launch {app_name}."


def _close_application(app_name: str) -> str:
    """Gracefully close an app by process name, escalating SIGTERM -> killall -> SIGKILL."""
    proc_name = app_name.lower().replace(" ", "")
    for cmd, label in [
        (["pkill", "-TERM", "-i", proc_name], "Sent close signal to"),
        (["killall", "-q", proc_name], "Closed"),
        (["pkill", "-KILL", "-i", proc_name], "Forcefully terminated"),
    ]:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return f"{label} {app_name}."
    return f"Could not find a running process matching '{app_name}'."


def register(mcp) -> None:
    @mcp.tool()
    def tool_open_application(app_name: str) -> str:
        """Launch/find and open an application by its name.

        Searches .desktop files in /usr/share/applications and ~/.local/share/applications
        for a matching application, then launches it via GLib's DesktopAppInfo.

        Args:
            app_name: Name of the application to open (e.g. "Firefox", "Terminal",
                      "Files", "Calculator").
        """
        return _open_application(app_name)

    @mcp.tool()
    def tool_close_application(app_name: str) -> str:
        """Close an application gracefully, falling back to force kill if needed.

        Sends a SIGTERM first, then tries killall, then SIGKILL as a last resort.

        Args:
            app_name: Name of the application to close (e.g. "Firefox", "Terminal").
        """
        return _close_application(app_name)
