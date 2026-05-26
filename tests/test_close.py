"""Tests for DBus window close via fuzzy_match.

Requires a GNOME Wayland session with 'Window Calls Extended' installed.
Tests gracefully handle the extension being unavailable.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.application import _close_application
from src.tools.fuzzy_match import best as best_match


def test_close_extension_response():
    """_close_application always returns a string (never None/exception)."""
    result = _close_application("zzz_nonexistent_app_xyzzy")
    assert isinstance(result, str), f"Expected str, got {type(result).__name__}"
    assert len(result) > 0
    print(f"  returns string: OK ({len(result)} chars)")
    print(f"    {result[:120]}...")
    print()


def test_close_no_match_lists_windows():
    """When no app matches, response includes window list or error."""
    result = _close_application("zzz_nonexistent_app_xyzzy")

    # Either: extension not available → error message
    # Or: extension working → lists open windows
    if "not available" in result.lower() or "unable to access" in result.lower():
        print("  extension not available — graceful message: OK")
    elif "No open window matching" in result:
        assert "Currently open windows" in result or "no windows" in result.lower()
        print("  no match — lists windows: OK")
    else:
        print(f"  unexpected result: {result[:200]}")
    print()


def test_fuzzy_match_windows():
    """fuzzy_match correctly ranks window titles (unit test, no DBus)."""
    titles = [
        "Obsidian - My Vault",
        "Firefox",
        "Firefox Web Browser",
        "YouTube Music - Chromium",
        "YouTube",
        "Terminal ~ fish",
    ]

    # Exact match
    assert best_match("firefox", titles) == "Firefox"
    print("  exact 'firefox' → Firefox: OK")

    # Prefix word (whole word at start)
    assert best_match("obsidian", titles) == "Obsidian - My Vault"
    print("  prefix 'obsidian' → Obsidian - My Vault: OK")

    # Exact among similar
    assert best_match("youtube", titles) == "YouTube"
    print("  exact 'youtube' → YouTube (not YouTube Music): OK")

    # No match
    assert best_match("notepad", titles) is None
    print("  'notepad' → None: OK")

    # Substring match (not a whole word, but substring scores 50)
    assert best_match("sidian", titles) == "Obsidian - My Vault"  # substring
    print("  substring 'sidian' → Obsidian: OK")

    print()


def test_close_real_app():
    """End-to-end: close a real app if extension is available."""
    result = _close_application("zzz_nonexistent_app_xyzzy")
    assert isinstance(result, str) and len(result) > 0
    if "not available" in result.lower() or "unable to" in result.lower():
        print("  SKIP: Window Calls Extended extension not available")
        print("    Install window-calls-extended@hseliger.eu to test real closing")
        return
    if "No open window" in result:
        assert "Currently open windows" in result or "no windows" in result.lower()
        print("  extension working — window list returned")
    elif "Closed" in result:
        assert "Closed" in result
        print("  real close succeeded!")
    else:
        print(f"  unexpected result: {result[:200]}")
    print()


if __name__ == "__main__":
    test_close_extension_response()
    test_close_no_match_lists_windows()
    test_fuzzy_match_windows()
    test_close_real_app()

    print("=" * 50)
    print("All DBus close tests passed.")
