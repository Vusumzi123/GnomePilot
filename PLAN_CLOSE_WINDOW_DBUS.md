# Plan: Replace pkill with DBus Window Close

## Motivation

- `pkill` is unreliable for Electron/PWA apps whose process names don't match
  the app name (e.g., Obsidian runs as a path-based binary, not "obsidian")
- `pkill` can unintentionally close unrelated processes with similar names
- The "Window Calls Extended" GNOME Shell Extension already exposes a DBus
  interface for listing and closing windows by title — far more precise
- Confirmed working via `gdbus call` tests (see below)

## DBus Interface (Window Calls)

| Property | Value |
|---|---|
| Bus name | `org.gnome.Shell` |
| Object path | `/org/gnome/Shell/Extensions/Windows` |
| Interface | `org.gnome.Shell.Extensions.Windows` |
| Extension UUID | `window-calls@domandoman.xyz` |

### Methods

| Method | Signature | Returns | Description |
|---|---|---|---|
| `List()` | none → string | JSON string | Array of window objects |
| `Close(window_id)` | uint32 → none | void | Closes the window with the given ID |

### Window object structure (from `List()`)

```json
{
  "class": "firefox",
  "pid": 8715,
  "id": 1841104639,
  "focus": false,
  "title": "install openwebui portainer - Google Search — Mozilla Firefox"
}
```

Fields: `class`, `pid`, `id`, `focus`, `title`.

## Changes

### File: `src/tools/application.py`

#### 1. Add imports (top of file)

```python
import json
import dbus
```

`dbus` is already available (used by `vision.py` and `window_manager.py`).

#### 2. Add DBus constants (after existing globals, around line 20)

```python
WINDOWS_DBUS_BUS = "org.gnome.Shell"
WINDOWS_DBUS_PATH = "/org/gnome/Shell/Extensions/WindowsExt"
WINDOWS_DBUS_IFACE = "org.gnome.Shell.Extensions.WindowsExt"
```

#### 3. Add `_close_via_dbus(app_name)` helper (before `_close_application`)

```python
def _close_via_dbus(app_name: str) -> str | None:
    """Close an app by matching its window title via Window Calls Extended.

    Calls the GNOME Shell Extension's List() method to enumerate all open
    windows, then matches app_name against each window's title field
    (case-insensitive substring).  Closes the first matching window via
    Close(window_id).

    Returns a user-facing message on success or failure.
    Returns None only if the extension is not available (so the caller
    can inform the user).
    """
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(WINDOWS_DBUS_BUS, WINDOWS_DBUS_PATH)
        iface = dbus.Interface(proxy, WINDOWS_DBUS_IFACE)
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
                f"The 'Window Calls Extended' GNOME Shell Extension is not available. "
                f"Please install it from extensions.gnome.org and restart your session. "
                f"(DBus error: {exc})"
            )
        return f"DBus error while listing windows: {exc}"
    except Exception:
        return None

    try:
        windows = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return f"Could not parse the window list returned by the GNOME Shell Extension."

    if not windows:
        return f"No windows are currently open."

    search = app_name.lower().strip()

    # First pass: exact title match
    for w in windows:
        title = (w.get("title") or "").lower().strip()
        if title == search:
            try:
                iface.Close(w["id"])
            except Exception as exc:
                return f"Found window '{w.get('title')}' but failed to close it: {exc}"
            return f"Closed {w.get('title')}."

    # Second pass: substring match
    for w in windows:
        title = w.get("title") or ""
        if search in title.lower():
            try:
                iface.Close(w["id"])
            except Exception as exc:
                return f"Found window '{title}' but failed to close it: {exc}"
            return f"Closed {title}."

    # No match — return the full window list so the assistant can help the user
    titles = [w.get("title", "?") for w in windows]
    listing = "\n".join(f"  • {t}" for t in titles)
    return (
        f"No open window matching '{app_name}' was found.\n\n"
        f"Currently open windows ({len(windows)}):\n{listing}"
    )
```

**Matching strategy:**
1. Exact title match (case-insensitive) — e.g., "firefox" matches "Firefox"
2. Substring match — e.g., "obsidian" matches "Obsidian - My Vault"
3. No match → return full list of open windows so the assistant can guide the user

**Error cases handled:**

| Scenario | Return value |
|---|---|
| Extension not installed/active | `"The 'Window Calls Extended' GNOME Shell Extension is not available..."` |
| DBus call itself fails | `"DBus error while listing windows: {exc}"` |
| List() returns unparseable | `"Could not parse the window list..."` |
| No windows open at all | `"No windows are currently open."` |
| Exact title match found | `"Closed Firefox."` |
| Substring match found | `"Closed Obsidian - My Vault."` |
| No match found | `"No open window matching 'xyz' was found.\n\nCurrently open windows (8):\n  • Firefox\n  • ..."` |
| Close() fails after match | `"Found window 'Obsidian' but failed to close it: {exc}"` |

#### 4. Replace `_close_application` entirely

**Remove lines 175–186** (the entire pkill/killall function).

**Replace with:**

```python
def _close_application(app_name: str) -> str:
    """Close an application by matching its window title via GNOME Shell Extension.

    Uses the Window Calls Extended DBus interface to list all open windows and
    close the one whose title matches the requested app name.  No pkill/killall
    fallback — if the extension can't find or close the window, the assistant
    tells the user exactly what happened and what windows are available.
    """
    result = _close_via_dbus(app_name)
    if result is not None:
        return result
    return (
        f"Unable to access the window management service. "
        f"Please ensure the 'Window Calls Extended' GNOME Shell Extension "
        f"is installed and enabled."
    )
```

#### 5. Update `tool_close_application` docstring

**Replace the docstring in `register()` (lines 206–213):**

```python
    @mcp.tool()
    def tool_close_application(app_name: str) -> str:
        """Close an application by matching its window title.

        Uses the GNOME Shell 'Window Calls Extended' extension to list all
        open windows and close the one whose title matches the given name.
        Reports which window was closed, or lists open windows if no match
        is found so the user can pick the right one.

        Args:
            app_name: Name of the application to close (e.g. "Firefox",
                      "Terminal", "Obsidian").
        """
        return _close_application(app_name)
```

#### 6. Remove unused helpers (if not used elsewhere)

Check if any of these are ONLY used by the old `_close_application`:

| Function | Used by | Keep? |
|---|---|---|
| `_close_application` | `tool_close_application` | Replaced |
| `_close_via_dbus` | `_close_application` | New |

No other code depends on pkill/killall. `subprocess` is still used by `_open_application` for the Exec= fallback (line 154). Keep `subprocess` import.

No imports to remove.

### File: `prompts/general.md`

Update the tool description to reflect the DBus-only approach:

**Change from:**
```
## Tools Available
You have tools to:
- Open and close applications
- Search and install system packages (pacman / AUR)
- Move windows between workspaces
```

**To:**
```
## Tools Available
You have tools to:
- Open applications (via desktop files)
- Close applications (by matching window title)
- Search and install system packages (pacman / AUR)
- Move windows between workspaces
```

And update the tool behavior instructions. Add after the existing behavior lines:

```
- When closing an app fails with a list of open windows, help the user pick the
  right one instead of retrying blindly
```

### Files affected

| File | Lines changed | Type |
|---|---|---|
| `src/tools/application.py` | ~-10, ~+80 | Remove pkill, add `_close_via_dbus`, replace `_close_application` |
| `prompts/general.md` | ~+3 | Update tool description |

No new files. No new dependencies (`dbus` already installed, `json` is stdlib).

## Testing

### Manual test (requires running GNOME session)

```bash
# 1. Verify the extension is active
gdbus call --session --dest org.gnome.Shell \
  --object-path /org/gnome/Shell/Extensions/WindowsExt \
  --method org.gnome.Shell.Extensions.WindowsExt.List

# 2. In the assistant CLI
You: open obsidian
Assistant: Opened Obsidian.
You: close obsidian
Assistant: Closed Obsidian - My Vault.

# 3. Try closing a non-existent app
You: close notepad
Assistant: No open window matching 'notepad' was found.
Currently open windows (8):
  • Firefox
  • Obsidian
  • Terminal
  ...

# 4. Try closing when extension isn't installed (uninstall first)
You: close firefox
Assistant: The 'Window Calls Extended' GNOME Shell Extension is not available...
```

### Automated test (new test_phase4.py)

```python
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from src.tools.application import _close_via_dbus

def test_close_via_dbus_empty():
    """Returns message when no windows match."""
    result = _close_via_dbus("zzz_nonexistent_app_zzz")
    assert result is not None
    assert "No open window matching" in result or "not available" in result or \
           "no windows" in result.lower()
    print("PASSED: _close_via_dbus handles no-match gracefully")

def test_close_via_dbus_real():
    """Close a real window via DBus."""
    result = _close_via_dbus("terminal")
    print(f"Result: {result}")
    # Should either succeed or list windows — never crash
    assert result is not None

if __name__ == "__main__":
    test_close_via_dbus_empty()
    test_close_via_dbus_real()
    print("=" * 40)
    print("Phase 4 close-via-DBus tests complete.")
```

## Rollback

If the Window Calls Extended extension is not installed, the assistant will tell the user:

> The 'Window Calls Extended' GNOME Shell Extension is not available. Please
> install it from extensions.gnome.org and restart your session.

To restore pkill fallback, revert `_close_application` to the old implementation.

## Dependencies

- No new Python packages
- Requires GNOME Shell Extension: `window-calls-extended@hseliger.eu`
  (already installed in this environment)
