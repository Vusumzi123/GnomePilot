"""Skill: GNOME Window management via DBus Shell Extension.

Requires the 'os-assistant@cachyos' GNOME Shell Extension to be installed and
enabled. The extension exports the org.gnome.Shell.Extensions.Assistant DBus
interface at /org/gnome/Shell/Extensions/Assistant.

Register with `register(mcp)` -- called automatically by the plugin loader.
"""

import dbus

from ._registry import tool

DBUS_NAME = "org.gnome.Shell"
DBUS_PATH = "/org/gnome/Shell/Extensions/Assistant"
DBUS_IFACE = "org.gnome.Shell.Extensions.Assistant"

EXTENSION_HELP = (
    "The GNOME Shell Extension 'os-assistant@cachyos' is not active. "
    "Please ensure the extension is installed in "
    "~/.local/share/gnome-shell/extensions/os-assistant@cachyos/ "
    "and restart your GNOME session (log out and back in)."
)


def _call_move_window(app_name: str, workspace_index: int) -> str:
    """Call the GNOME Shell Extension via DBus to move a window to a workspace.

    workspace_index is 0-based (workspace 1 = index 0). The extension matches
    by window title or WM_CLASS (case-insensitive).
    """
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(DBUS_NAME, DBUS_PATH)
        iface = dbus.Interface(proxy, DBUS_IFACE)
        success = iface.MoveWindowToWorkspace(app_name, workspace_index)
        if success:
            return f"Moved window matching '{app_name}' to workspace {workspace_index + 1}."
        return f"Could not find a window matching '{app_name}'."
    except dbus.exceptions.DBusException as e:
        name = e.get_dbus_name()
        if name in (
            "org.freedesktop.DBus.Error.ServiceUnknown",
            "org.freedesktop.DBus.Error.NameHasNoOwner",
        ):
            return f"{EXTENSION_HELP}\n(DBus error: {e})"
        return f"DBus error: {e}"
    except Exception as e:
        return f"Failed to move window: {e}"



@tool()
def tool_move_window_to_workspace(app_name: str, workspace_index: int) -> str:
    """Move a window matching the given name to a specific workspace.

    Workspace indices are 0-based -- workspace 1 is index 0, workspace 2
    is index 1, etc.  The match is case-insensitive and checks both the
    window title and the application's WM_CLASS.

    Requires the 'os-assistant@cachyos' GNOME Shell Extension to be active.

    Args:
        app_name: Name of the application/window to move (e.g. "Terminal",
                  "Firefox", "Files").
        workspace_index: 0-based index of the target workspace (0 = first
                         workspace, 1 = second, etc.).
    """
    return _call_move_window(app_name, workspace_index)
