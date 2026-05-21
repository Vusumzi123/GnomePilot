"""Desktop file index — scan .desktop files and resolve app name lookups."""

import shlex
import shutil
from pathlib import Path

from .fuzzy_match import score as fuzzy_score

DESKTOP_DIRS = [
    Path("/usr/share/applications"),
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
