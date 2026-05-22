"""Skill: Application management (launch & close desktop apps).

Auto-discovered via @tool() decorator — no manual wiring needed.
"""

import json
import shlex
import subprocess
from pathlib import Path

import dbus
from gi.repository import Gio

from .desktop_index import resolve
from .fuzzy_match import best as best_match
from ._registry import tool

_WINDOWS_BUS = "org.gnome.Shell"
_WIN_PATH = "/org/gnome/Shell/Extensions/Windows"
_WIN_IFACE = "org.gnome.Shell.Extensions.Windows"


def _open_application(app_name: str) -> str:
    """Find a .desktop file for app_name and launch it.

    Prefers parsing the Exec= line and spawning via subprocess.Popen with
    redirected stdio — this prevents child process output from leaking into
    the MCP server's JSON-RPC channel (critical for Chromium-based PWAs that
    print "Opening in existing browser session." on launch).

    Falls back to Gio.DesktopAppInfo.launch() only when Exec= is unavailable.
    """
    desktop_file = resolve(app_name)
    if desktop_file is None:
        return f"Could not find an application matching '{app_name}'."

    exec_line = _read_exec_line(desktop_file)
    if exec_line:
        try:
            subprocess.Popen(
                shlex.split(exec_line), start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return f"Opened {app_name}."
        except Exception as e:
            return f"Failed to launch {app_name}: {e}"

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
    """Close an application by matching its window title via GNOME Shell Extension.

    Uses the Window Calls Extended DBus interface to list all open windows,
    matches the best-scoring title via fuzzy_match, and closes it.
    If no match is found the full window list is returned so the user or
    assistant can pick the right one.
    """
    # 1. Fetch window list via DBus
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(_WINDOWS_BUS, _WIN_PATH)
        iface = dbus.Interface(proxy, _WIN_IFACE)
        raw = iface.List()
    except dbus.exceptions.DBusException as exc:
        name = exc.get_dbus_name()
        if name in (
            "org.freedesktop.DBus.Error.ServiceUnknown",
            "org.freedesktop.DBus.Error.NameHasNoOwner",
            "org.freedesktop.DBus.Error.UnknownMethod",
            "org.freedesktop.DBus.Error.UnknownObject",
        ):
            return (
                f"The 'Window Calls' GNOME Shell Extension "
                f"is not available. Please install it from "
                f"extensions.gnome.org and restart your session. "
                f"(DBus: {exc})"
            )
        return f"DBus error while listing windows: {exc}"
    except Exception as exc:
        return f"Unable to access window list: {exc}"

    # 2. Parse window list
    try:
        windows = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return "Could not parse the window list from the GNOME Shell Extension."

    if not windows:
        return "No windows are currently open."

    # 3. Fuzzy-match the best window title
    titles = [w.get("title", "") for w in windows]
    matched_title = best_match(app_name, titles, threshold=50)

    if matched_title is None:
        listing = "\n".join(f"  • {t}" for t in titles if t)
        return (
            f"No open window matching '{app_name}' was found.\n\n"
            f"Currently open windows ({len(windows)}):\n{listing}"
        )

    # 4. Close the matched window
    for w in windows:
        if w.get("title") == matched_title:
            try:
                iface.Close(w["id"])
            except Exception as exc:
                return f"Found window '{matched_title}' but failed to close it: {exc}"
            return f"Closed {matched_title}."

    # Shouldn't reach here, but safety net
    return f"Matched '{matched_title}' but could not find its window ID."



@tool()
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


@tool()
def tool_close_application(app_name: str) -> str:
    """Close an application by matching its window title.

    Uses the GNOME Shell 'Window Calls' extension to list all open
    windows, fuzzy-matches the best title, and closes the window.  Reports
    the closed window title, or lists all open windows if no match is found.

    Args:
        app_name: Name of the application to close (e.g. "Firefox",
                  "Terminal", "Obsidian", "YouTube Music").
    """
    return _close_application(app_name)
