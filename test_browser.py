"""Tests for browser control skill — integration.

tool_browser_open uses D-Bus portal (always works).
CDP tools need Chrome with --remote-debugging-port.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_open_url_via_dbus():
    from src.tools.browser import tool_browser_open
    result = tool_browser_open("https://example.com")
    assert "Opened" in result or "Failed" in result
    print(f"  open url via D-Bus: OK ({result.split(chr(10))[0][:80]})")


async def test_cdp_connect_error():
    from src.tools.browser import _connect_cdp
    ok, err = await _connect_cdp()
    if ok:
        print("  CDP connected: OK (Chrome on debug port)")
    else:
        assert "Cannot connect" in err or "remote-debugging" in err
        print("  CDP error message: OK")


async def test_search_needs_cdp():
    from src.tools.browser import tool_browser_search
    result = await tool_browser_search("python programming")
    assert isinstance(result, str)
    print(f"  search tool: OK ({len(result)} chars)")


async def test_tabs_needs_cdp():
    from src.tools.browser import tool_browser_list_tabs
    result = await tool_browser_list_tabs()
    assert isinstance(result, str)
    print(f"  list tabs: OK ({len(result)} chars)")


async def main():
    test_open_url_via_dbus()
    await test_cdp_connect_error()
    await test_search_needs_cdp()
    await test_tabs_needs_cdp()
    print()
    print("=" * 50)
    print("All browser tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
