"""Desktop file index — scan .desktop files and resolve app name lookups."""

import os
import re
import shlex
import shutil
from pathlib import Path

from .fuzzy_match import score as fuzzy_score

DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
    Path.home() / "Applications",
]

ALIASES = {"terminal": "console", "gnometerminal": "console", "texteditor": "gedit"}

_index: list[tuple[Path, str]] | None = None


def scan() -> list[tuple[Path, str]]:
    """Scan all desktop directories and return (path, display_name) tuples.

    Display name comes from the Name= field, falling back to the filename stem.
    Entries with a working Exec= binary are listed first (higher priority).
    Result is cached — call scan() repeatedly, it reuses the built index.
    """
    global _index
    if _index is not None:
        return _index

    entries: list[tuple[Path, str]] = []
    for d in DESKTOP_DIRS:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.suffix != ".desktop":
                continue
            name = _read_name(f) or f.stem
            entries.append((f, name))

    entries.sort(key=lambda e: _exec_exists(e[0]), reverse=True)
    _index = entries
    return entries


def resolve(app_name: str) -> Path | None:
    """Find the best-matching .desktop file for an app name.

    Uses fuzzy_match scoring against both the display Name and filename stem.
    Returns the highest-scoring path, or None if no entry scores >= 50.
    """
    search = ALIASES.get(app_name.lower().replace(" ", "").replace("-", ""))
    if search is None:
        search = app_name.lower().replace(" ", "").replace("-", "")

    best_score = 0
    best_path: Path | None = None

    for path, name in scan():
        dn = name.lower().replace(" ", "").replace("-", "")
        stem = path.stem.lower().replace(" ", "").replace("-", "")
        s = max(fuzzy_score(search, dn), fuzzy_score(search, stem))
        if s > best_score:
            best_score = s
            best_path = path

    return best_path if best_score >= 50 else None


def _read_name(path: Path) -> str | None:
    """Extract the Name= value from a .desktop file."""
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("Name="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None


def _exec_exists(path: Path) -> bool:
    """Check whether the first word of the Exec= line is an executable on PATH."""
    exec_line = _read_exec_line(path)
    if not exec_line:
        return False
    binary = shlex.split(exec_line)[0] if exec_line else ""
    return bool(binary and shutil.which(binary))


def validate_desktop_file(path: Path) -> bool:
    """Check a .desktop file is safe to execute.

    Files under system directories (/usr/share/applications,
    /usr/local/share/applications) are trusted. Files under user directories
    (~/.local/share/applications, ~/Applications) must be owned by the
    current user and not writable by group or others.
    """
    try:
        stat = path.stat()
        if stat.st_size == 0:
            return False

        uid = os.getuid()
        is_owner = stat.st_uid == uid

        perms = stat.st_mode & 0o777
        group_writable = bool(perms & 0o020)
        others_writable = bool(perms & 0o002)

        if group_writable or others_writable:
            return False

        parent = str(path.parent)
        if parent in ("/usr/share/applications", "/usr/local/share/applications"):
            return stat.st_uid == 0
        return is_owner
    except Exception:
        return False


def _read_exec_line(path: Path) -> str | None:
    """Extract the Exec= value, stripping all freedesktop field codes."""
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("Exec="):
                raw = line.split("=", 1)[1].strip()
                cleaned = re.sub(r'(?<!=)%[uUfFkci]|%%', '', raw).strip()
                return cleaned
    except Exception:
        pass
    return None
