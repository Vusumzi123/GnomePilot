"""Skill: Application management (launch & close desktop apps).

Register with `register(mcp)` -- called automatically by the plugin loader.
"""

import re
import shlex
import shutil
import subprocess
from pathlib import Path

from gi.repository import Gio

DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path.home() / ".local/share/applications",
    Path.home() / "Applications",
]

ALIASES = {"terminal": "console", "gnometerminal": "console", "texteditor": "gedit"}

_desktop_index: list[tuple[Path, str]] | None = None


def _build_index() -> list[tuple[Path, str]]:
    """Scan all desktop directories once and return (path, display_name) tuples.

    Display name is the Name= field value, falling back to the filename stem.
    Entries with a working Exec= binary are listed first (higher priority).
    """
    entries: list[tuple[Path, str]] = []
    for desktop_dir in DESKTOP_DIRS:
        if not desktop_dir.exists():
            continue
        for entry in desktop_dir.iterdir():
            if not entry.suffix == ".desktop":
                continue
            name = _read_desktop_name(entry) or entry.stem
            entries.append((entry, name))
    entries.sort(key=lambda e: _exec_exists(e[0]), reverse=True)
    return entries


def _get_index() -> list[tuple[Path, str]]:
    """Lazy-build the desktop file index (cached after first call)."""
    global _desktop_index
    if _desktop_index is None:
        _desktop_index = _build_index()
    return _desktop_index


def _match_score(search: str, target: str) -> int:
    """Score how well `search` matches `target` (higher = better).

    Scoring tiers:
      100 — exact match
       90 — target starts with search followed by word boundary or end
       70 — search appears as a whole word within target
       50 — search is a substring of target
        0 — no match
    """
    s = search.lower().strip()
    t = target.lower().strip()
    if not s or not t:
        return 0
    if s == t:
        return 100
    if re.match(rf"\b{re.escape(s)}\b", t):
        start = t.index(s)
        if start == 0 and (len(t) == len(s) or not t[len(s)].isalnum()):
            return 90
        return 70
    if s in t:
        return 50
    return 0


def _find_desktop_file(app_name: str) -> Path | None:
    """Find the best-matching .desktop file using a scored index lookup.

    Looks up the pre-built index of all desktop files, scores each candidate
    against the search term, and returns the highest-scoring match. Prefers
    exact Name= matches ("YouTube") over partial matches ("YouTube Music").
    """
    search = app_name.lower().replace(" ", "").replace("-", "")
    search = ALIASES.get(search, search)

    best_score = 0
    best_path: Path | None = None

    for path, name in _get_index():
        # Score against the display Name field
        dn = name.lower().replace(" ", "").replace("-", "")
        score_name = _match_score(search, dn)

        # Score against the filename stem (fallback)
        stem = path.stem.lower().replace(" ", "").replace("-", "")
        score_file = _match_score(search, stem)

        score = max(score_name, score_file)
        if score > best_score:
            best_score = score
            best_path = path

    return best_path if best_score >= 50 else None


def _exec_exists(path: Path) -> bool:
    """Check whether the first word of the Exec= line is an executable on PATH."""
    exec_line = _read_exec_line(path)
    if not exec_line:
        return False
    binary = shlex.split(exec_line)[0] if exec_line else ""
    return bool(binary and shutil.which(binary))


def _read_desktop_name(path: Path) -> str | None:
    """Extract the Name= value from a .desktop file."""
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("Name="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def _open_application(app_name: str) -> str:
    """Find a .desktop file for app_name and launch it via Gio.DesktopAppInfo.

    Falls back to parsing and executing the Exec= line directly if the GLib
    constructor returns NULL (e.g. for PWAs or custom launchers).
    """
    desktop_file = _find_desktop_file(app_name)
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
