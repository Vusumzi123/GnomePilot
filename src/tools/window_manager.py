"""Skill: GNOME Window management via Window Calls Shell Extension.

Uses the 'Window Calls' GNOME Shell Extension (window-calls@domandoman.xyz)
to list open windows, fuzzy-match by title, and move windows between workspaces.

Auto-discovered via @tool() decorator — no manual wiring needed.
"""

import json

import dbus

from ._registry import tool
from .fuzzy_match import best as best_match

_WIN_BUS = "org.gnome.Shell"
_WIN_PATH = "/org/gnome/Shell/Extensions/Windows"
_WIN_IFACE = "org.gnome.Shell.Extensions.Windows"


def _move_via_dbus(app_name: str, workspace_index: int) -> str:
    """Move a window to a workspace by fuzzy-matching its title via Window Calls.

    1. Lists all open windows via DBus.
    2. Fuzzy-matches app_name against window titles.
    3. Calls MoveToWorkspace(id, workspace_index) on the best match.
    4. Returns the full window list if no match is found.

    workspace_index is 0-based (workspace 1 = index 0).
    """
    # 1. Fetch window list
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(_WIN_BUS, _WIN_PATH)
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
                f"The 'Window Calls' GNOME Shell Extension is not available. "
                f"Please install it from extensions.gnome.org and restart "
                f"your session. (DBus: {exc})"
            )
        return f"DBus error while listing windows: {exc}"
    except Exception as exc:
        return f"Unable to access window list: {exc}"

    # 2. Parse + match
    try:
        windows = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return "Could not parse the window list from the GNOME Shell Extension."

    if not windows:
        return "No windows are currently open."

    titles = [w.get("title", "") for w in windows]
    matched_title = best_match(app_name, titles, threshold=50)

    if matched_title is None:
        listing = "\n".join(f"  • {t}" for t in titles if t)
        return (
            f"No open window matching '{app_name}' was found.\n\n"
            f"Currently open windows ({len(windows)}):\n{listing}"
        )

    # 3. Move to workspace
    for w in windows:
        if w.get("title") == matched_title:
            try:
                iface.MoveToWorkspace(w["id"], workspace_index)
            except Exception as exc:
                return f"Found window '{matched_title}' but failed to move it: {exc}"
            return f"Moved {matched_title} to workspace {workspace_index + 1}."

    return f"Matched '{matched_title}' but could not find its window ID."


@tool()
def tool_move_window_to_workspace(app_name: str, workspace_index: int) -> str:
    """Move a window matching the given name to a specific workspace.

    Uses the 'Window Calls' GNOME Shell Extension to list all open windows,
    fuzzy-matches the best title, and moves the window.

    Workspace indices are 0-based — workspace 1 is index 0, workspace 2
    is index 1, etc.

    Args:
        app_name: Name of the application/window to move (e.g. "Terminal",
                  "Firefox", "Files").
        workspace_index: 0-based index of the target workspace (0 = first
                         workspace, 1 = second, etc.).
    """
    return _move_via_dbus(app_name, workspace_index)
