"""Tests for src/tools/package_manager.py — install guides + search."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.package_manager import _install_package


def test_install_package_creates_md_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with patch("src.config.install_guides_dir", return_value=tmp_path):
            result = _install_package("htop")
        path = Path(result)
        assert path.exists()
        assert path.suffix == ".md"
        content = path.read_text()
        assert "sudo pacman -S htop" in content
        assert "yay -S htop" in content
        assert "# Install Guide: htop" in content
    print("  install guide creates MD: OK")


def test_install_package_sanitizes_filename():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with patch("src.config.install_guides_dir", return_value=tmp_path):
            result = _install_package("some/evil<>path")
        path = Path(result)
        assert "some_evil__path" in path.stem
        assert "../" not in result
        assert path.exists()
    print("  install guide sanitizes filename: OK")


def test_install_package_empty_name_handled():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with patch("src.config.install_guides_dir", return_value=tmp_path):
            result = _install_package("")
        path = Path(result)
        assert path.exists()
        content = path.read_text()
        assert "sudo pacman -S " in content
    print("  install guide empty name: OK")


def test_install_package_tool_returns_path():
    from src.tools.package_manager import tool_install_package
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with patch("src.config.install_guides_dir", return_value=tmp_path):
            result = tool_install_package("htop")
            assert ".md" in result
    print("  tool_install_package returns path: OK")


if __name__ == "__main__":
    test_install_package_creates_md_file()
    test_install_package_sanitizes_filename()
    test_install_package_empty_name_handled()
    test_install_package_tool_returns_path()
    print()
    print("=" * 50)
    print("All package_manager tests passed.")
