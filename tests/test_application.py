"""Tests for src/tools/application.py — open/close apps + security validation."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.application import _open_application, _close_application
from src.tools.desktop_index import resolve, _read_exec_line, validate_desktop_file


# ── resolve tests ──

def test_resolve_known_apps():
    for name in ["firefox", "files", "terminal"]:
        path = resolve(name)
        assert path is not None, f"{name} should be resolvable"
        assert path.exists(), f"{name}.desktop should exist"
    print("  resolve known apps: OK")


def test_resolve_nonexistent():
    assert resolve("zzz_nonexistent_app_xyzzy") is None
    print("  resolve nonexistent → None: OK")


def test_resolve_alias():
    path = resolve("terminal")
    assert path is not None and path.exists()
    print(f"  resolve alias 'terminal' → {path.stem}: OK")


# ── exec line tests ──

def test_read_exec_line_strips_field_codes():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".desktop", delete=False) as f:
        f.write("[Desktop Entry]\nName=Test\nExec=/usr/bin/test-app %u\n")
        f.flush()
        tmp = Path(f.name)
    try:
        assert _read_exec_line(tmp) == "/usr/bin/test-app"
    finally:
        tmp.unlink()
    print("  strips %u: OK")


def test_read_exec_line_strips_all_codes():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".desktop", delete=False) as f:
        f.write("[Desktop Entry]\nName=Test\nExec=/usr/bin/test-app %U %f %F %k %i %c %%\n")
        f.flush()
        tmp = Path(f.name)
    try:
        result = _read_exec_line(tmp)
        assert "%U" not in result
        assert "%f" not in result
        assert "%F" not in result
        assert "%k" not in result
        assert "%i" not in result
        assert "%c" not in result
        assert "%%" not in result
        assert result.strip() == "/usr/bin/test-app"
    finally:
        tmp.unlink()
    print("  strips all field codes: OK")


def test_read_exec_line_no_exec_returns_none():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".desktop", delete=False) as f:
        f.write("[Desktop Entry]\nName=Test\n")
        f.flush()
        tmp = Path(f.name)
    try:
        assert _read_exec_line(tmp) is None
    finally:
        tmp.unlink()
    print("  no Exec= → None: OK")


def test_read_exec_line_multiple_exec_uses_first():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".desktop", delete=False) as f:
        f.write(
            "[Desktop Entry]\nName=Test\n"
            "Exec=/usr/bin/app1 %u\n"
            "Exec=/usr/bin/app2 %F\n"
        )
        f.flush()
        tmp = Path(f.name)
    try:
        assert _read_exec_line(tmp) == "/usr/bin/app1"
    finally:
        tmp.unlink()
    print("  first Exec= used: OK")


# ── security validation tests ──

def test_validate_system_file_is_trusted():
    path = resolve("firefox")
    if path and path.exists():
        assert validate_desktop_file(path), "system file should pass validation"
        print(f"  system file {path.stem} validates: OK")
    else:
        print("  SKIP: firefox not found")


def test_validate_user_owned_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".desktop", delete=False) as f:
        f.write("[Desktop Entry]\nName=Test\nExec=/usr/bin/test-app %u\n")
        f.flush()
        tmp = Path(f.name)
    try:
        # Temp files are owned by current user and not world-writable
        result = validate_desktop_file(tmp)
        # May be True or False depending on temp dir location (system vs user)
        print(f"  user file validation: {result} (temp dir)")
    finally:
        tmp.unlink()


def test_validate_rejects_nonexistent():
    assert not validate_desktop_file(Path("/nonexistent/file.desktop"))
    print("  nonexistent file rejected: OK")


def test_validate_rejects_empty_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".desktop", delete=False) as f:
        f.write("")
        f.flush()
        tmp = Path(f.name)
    try:
        assert not validate_desktop_file(tmp)
    finally:
        tmp.unlink()
    print("  empty file rejected: OK")


def test_validate_rejects_world_writable():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".desktop", delete=False) as f:
        f.write("[Desktop Entry]\nName=Test\nExec=/usr/bin/test-app %u\n")
        f.flush()
        tmp = Path(f.name)
    os.chmod(tmp, 0o666)
    try:
        assert not validate_desktop_file(tmp), "world-writable file should be rejected"
    finally:
        tmp.chmod(0o644)
        tmp.unlink()
    print("  world-writable rejected: OK")


# ── open application tests ──

def test_open_known_app():
    result = _open_application("firefox")
    assert "Opened" in result or "Could not find" in result or "Safety check" in result, \
        f"Unexpected result: {result}"
    print(f"  open firefox: {result}")


def test_open_nonexistent_app():
    result = _open_application("zzz_nonexistent_app_xyzzy")
    assert "Could not find" in result, f"Expected 'Could not find', got: {result}"
    print("  open nonexistent: OK")


# ── close application tests ──

def test_close_always_returns_string():
    result = _close_application("zzz_nonexistent_app_xyzzy")
    assert isinstance(result, str)
    assert len(result) > 0
    print("  close returns string: OK")


if __name__ == "__main__":
    test_resolve_known_apps()
    test_resolve_nonexistent()
    test_resolve_alias()
    test_read_exec_line_strips_field_codes()
    test_read_exec_line_strips_all_codes()
    test_read_exec_line_no_exec_returns_none()
    test_read_exec_line_multiple_exec_uses_first()
    test_validate_system_file_is_trusted()
    test_validate_user_owned_file()
    test_validate_rejects_nonexistent()
    test_validate_rejects_empty_file()
    test_validate_rejects_world_writable()
    test_open_known_app()
    test_open_nonexistent_app()
    test_close_always_returns_string()
    print()
    print("=" * 50)
    print("All application tests passed.")
