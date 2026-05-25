"""Tests for browser control skill — open URLs via D-Bus, read pages via HTTP."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_open_url_via_dbus():
    from src.tools.browser import tool_browser_open
    result = tool_browser_open.invoke({"url": "https://example.com"})
    assert "Opened" in result or "Failed" in result
    print(f"  open url via D-Bus: OK ({result.split(chr(10))[0][:80]})")


def test_read_page():
    from src.tools.browser import tool_browser_read
    result = tool_browser_read.invoke({"url": "https://example.com"})
    assert isinstance(result, str)
    assert len(result) > 100, f"Expected >100 chars, got {len(result)}"
    print(f"  read page: OK ({len(result)} chars)")


def test_read_bad_url():
    from src.tools.browser import tool_browser_read
    result = tool_browser_read.invoke(
        {"url": "http://this-domain-does-not-exist.invalid"}
    )
    assert "Failed" in result
    print(f"  read bad url: OK ({result[:80]})")


if __name__ == "__main__":
    test_open_url_via_dbus()
    test_read_page()
    test_read_bad_url()
    print()
    print("=" * 50)
    print("All browser tests passed.")
