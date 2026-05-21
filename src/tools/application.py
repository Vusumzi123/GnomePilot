"""Skill: Application management (launch & close desktop apps).

Register with `register(mcp)` -- called automatically by the plugin loader.
"""

import shlex
import subprocess
from pathlib import Path

from gi.repository import Gio

from .desktop_index import resolve


def _open_application(app_name: str) -> str:
    """Find a .desktop file for app_name and launch it via Gio.DesktopAppInfo.

    Falls back to parsing and executing the Exec= line directly if the GLib
    constructor returns NULL (e.g. for PWAs or custom launchers).
    """
    desktop_file = resolve(app_name)
    if desktop_file is None:
        return f"Could not find an application matching '{app_name}'."

    app_info = None
    try:
        app_info = Gio.DesktopAppInfo.new_from_filename(str(desktop_file))
    except TypeError:
        pass

    if app_info is not None:
        launched = app_info.launch()
        if launched:
            return f"Opened {app_name}."
        return f"Failed to launch {app_name} via DesktopAppInfo."

    exec_line = _read_exec_line(desktop_file)
    if exec_line:
        try:
            subprocess.Popen(shlex.split(exec_line), start_new_session=True)
            return f"Opened {app_name}."
        except Exception as e:
            return f"Failed to launch {app_name}: {e}"

    return f"Failed to load desktop file for '{app_name}' (no valid Exec line)."


def _read_exec_line(path: Path) -> str | None:
    """Extract the Exec= value from a .desktop file, stripping field codes."""
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("Exec="):
                raw = line.split("=", 1)[1].strip()
                return raw.replace("%U", "").replace("%u", "").replace("%F", "").replace("%f", "").strip()
    except Exception:
        pass
    return None


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

        Searches .desktop files in /usr/share/applications, ~/.local/share/applications,
        and ~/Applications/ for a matching application. Matches by filename first,
        then by the Name= field inside .desktop files (supports PWAs with numeric IDs).
        Launches via GLib's DesktopAppInfo.

        Args:
            app_name: Name of the application to open (e.g. "Firefox", "Terminal",
                      "YouTube", "Files", "Calculator").
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
