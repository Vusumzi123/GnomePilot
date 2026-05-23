"""Skill: Browser automation via Playwright CDP + D-Bus OpenURI.

tool_browser_open uses D-Bus org.freedesktop.portal.OpenURI to open URLs
in your system browser — guaranteed visible, persistent window.

Other tools (search, read, tabs) connect to your system Chrome via CDP
(Chrome DevTools Protocol).  Requires Chrome launched with:

    chromium --remote-debugging-port=9222

Auto-discovered via @tool() decorator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import dbus
from loguru import logger

from src.config import debug_enabled, browser_cdp_port
from ._registry import tool

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page


# ── CDP connection state ──────────────────────────────────────────────────

@dataclass
class _BrowserSession:
    browser: Browser
    pages: list[Page] = field(default_factory=list)

    @property
    def active(self) -> Page | None:
        return self.pages[-1] if self.pages else None


_session: _BrowserSession | None = None


async def _connect_cdp():
    """Connect to Chrome via CDP, auto-launching if needed. Returns (ok, error)."""
    global _session

    if _session is not None:
        logger.info("CDP session alive: pages={}", len(_session.pages))
        return True, ""

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False, "Playwright is not installed. Run: pip install playwright"

    port = browser_cdp_port()
    cdp_url = f"http://localhost:{port}"

    pw = await async_playwright().start()

    # Try connecting to an already-running Chrome first
    logger.info("Connecting CDP to {}", cdp_url)
    try:
        browser = await pw.chromium.connect_over_cdp(cdp_url)
        logger.info("CDP connected to existing Chrome")
    except Exception:
        logger.info("No Chrome on CDP, launching one")
        try:
            browser = await pw.chromium.launch(
                headless=False,
                args=[
                    f"--remote-debugging-port={port}",
                    "--disable-gpu-sandbox",
                ],
            )
            logger.info("Launched Chrome with CDP on port {}", port)
        except Exception as exc:
            await pw.stop()
            return False, (
                f"Cannot launch Chromium. Is it installed? "
                f"(sudo pacman -S chromium)\n"
                f"Error: {exc}"
            )

    pages = browser.contexts[0].pages if browser.contexts else [await browser.new_page()]

    _session = _BrowserSession(browser=browser, pages=pages)
    browser.on("disconnected", lambda: logger.info("CDP browser disconnected"))
    logger.info("CDP connected: pages={}", len(_session.pages))
    return True, ""


def _sync_ensure_session():
    """Sync check for D-Bus tools (just checks if CDP session exists, no-op for open)."""
    return True, ""


# ── Tier 1: D-Bus OpenURI (sync, always works) ───────────────────────────

def _dbus_open_url(url: str) -> str:
    """Open a URL in the system default browser via D-Bus portal."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    logger.info("DBus OpenURI: {}", url)
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
        )
        iface = dbus.Interface(proxy, "org.freedesktop.portal.OpenURI")
        iface.OpenURI("", url, {})
        return f"Opened {url} in your browser."
    except dbus.exceptions.DBusException as exc:
        name = exc.get_dbus_name() or ""
        if "ServiceUnknown" in name or "NameHasNoOwner" in name:
            return (
                f"Desktop portal not available. Cannot open {url}.\n"
                f"DBus: {exc}"
            )
        return f"Failed to open {url} via portal: {exc}"
    except Exception as exc:
        return f"Failed to open {url}: {exc}"


# ── Tier 2: CDP tools (async, needs Chrome on debug port) ────────────────

async def _get_page(index: int = -1):
    """Get a CDP page by index (-1 = last/active)."""
    ok, err = await _connect_cdp()
    if not ok:
        return None, err

    assert _session is not None

    if index < 0:
        index = max(0, len(_session.pages) + index)

    if index >= len(_session.pages):
        contexts = _session.browser.contexts
        ctx = contexts[0] if contexts else await _session.browser.new_context()
        page = await ctx.new_page()
        _session.pages.append(page)
        return page, ""

    return _session.pages[index], ""


async def _navigate(page, url: str, timeout: int = 15000) -> str:
    """Navigate a CDP page to a URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    logger.info("CDP navigate: {}", url)

    try:
        await page.goto(url, timeout=timeout)
        await page.bring_to_front()
        title = await page.title()
        logger.info("CDP nav OK: title={!r}", title)
        return f"Loaded: {title} ({page.url})"
    except Exception as exc:
        return f"Failed to load {url}: {exc}"


async def _read_text(page, max_chars: int = 4000) -> str:
    """Extract visible text from a CDP page."""
    try:
        text = await page.inner_text("body")
    except Exception:
        text = ""

    if not text:
        return "(page is empty or still loading)"

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars]"

    return text


async def _refresh_pages():
    """Re-scan browser contexts for the current page list (picks up user-opened tabs)."""
    global _session
    if _session is None:
        return
    try:
        contexts = _session.browser.contexts
        if contexts:
            _session.pages = list(contexts[0].pages)
    except Exception:
        pass


# ── Tool functions ────────────────────────────────────────────────────────

@tool()
def tool_browser_open(url: str) -> str:
    """Open a URL in your default web browser.

    Uses the desktop portal to open in your real browser window —
    guaranteed visible and persistent.

    Args:
        url: The web address to open (e.g. "github.com", "https://example.com").
    """
    logger.info("Browser open: url={!r}", url)
    return _dbus_open_url(url)


@tool()
async def tool_browser_search(query: str) -> str:
    """Search the web using DuckDuckGo in your Chrome browser via CDP.

    Requires Chrome running with --remote-debugging-port.
    Navigates to DuckDuckGo search results and returns page content.

    Args:
        query: The search terms (e.g. "weather in London today").
    """
    page, err = await _get_page()
    if page is None:
        return err

    logger.info("Browser search: query={!r}", query)

    engine_url = f"https://duckduckgo.com/?{urlencode({'q': query})}"
    status = await _navigate(page, engine_url)

    try:
        for selector in ("article[data-testid=\"result\"]", ".result__body", ".result"):
            try:
                await page.wait_for_selector(selector, timeout=3000)
                break
            except Exception:
                continue
    except Exception:
        pass

    result_limit = 2000
    text = await _read_text(page, max_chars=result_limit)
    return f"{status}\n\n{text}" if text else status


@tool()
async def tool_browser_read_page(max_chars: int = 4000) -> str:
    """Read the visible text content of the current Chrome tab via CDP.

    Requires Chrome running with --remote-debugging-port.

    Args:
        max_chars: Maximum characters to return (default 4000, max 20000).
    """
    page, err = await _get_page()
    if page is None:
        return err

    await page.bring_to_front()
    logger.info("Browser read page: max_chars={}, url={}", max_chars, page.url)
    text = await _read_text(page, min(max_chars, 20000))
    if debug_enabled():
        logger.debug("Page content for {}\n{}", page.url, text)
    return text


@tool()
async def tool_browser_new_tab(url: str = "") -> str:
    """Open a new tab in Chrome via CDP.

    Requires Chrome running with --remote-debugging-port.

    Args:
        url: Optional URL to load.  Empty = blank page.
    """
    _, err = await _connect_cdp()
    if err:
        return err

    assert _session is not None
    logger.info("Browser new tab: url={!r}", url)

    contexts = _session.browser.contexts
    ctx = contexts[0] if contexts else await _session.browser.new_context()
    page = await ctx.new_page()
    _session.pages.append(page)

    if url:
        return await _navigate(page, url)
    return "New tab opened (blank page)."


@tool()
async def tool_browser_close_tab() -> str:
    """Close the current Chrome tab via CDP. Keeps browser open.

    Requires Chrome running with --remote-debugging-port.
    """
    _, err = await _connect_cdp()
    if err:
        return err

    assert _session is not None
    await _refresh_pages()

    logger.info("Browser close tab: pages={}", len(_session.pages))

    if len(_session.pages) <= 1:
        title = await _session.active.title() if _session.active else "untitled"
        return (
            f"Cannot close the last tab ({title}). "
            f"Close the browser window manually instead."
        )

    page = _session.pages.pop()
    title = await page.title() if page else "untitled"
    try:
        await page.close()
    except Exception:
        pass
    return f"Closed tab: {title}."


@tool()
async def tool_browser_list_tabs() -> str:
    """List all open Chrome tabs with their titles and URLs via CDP.

    Requires Chrome running with --remote-debugging-port.
    """
    _, err = await _connect_cdp()
    if err:
        return err

    assert _session is not None
    await _refresh_pages()

    logger.info("Browser list tabs: count={}", len(_session.pages))

    lines = []
    for i, page in enumerate(_session.pages, 1):
        try:
            title = await page.title()
            url = page.url
        except Exception:
            title, url = "(unavailable)", ""
        marker = " <<< current" if page == _session.active else ""
        lines.append(f"{i}. {title}\n   {url}{marker}")

    return "\n".join(lines)


@tool()
async def tool_browser_close_browser() -> str:
    """Close the CDP browser connection (does not close the actual Chrome window)."""
    global _session
    logger.info("CDP disconnect requested")
    try:
        if _session:
            await _session.browser.close()
    except Exception:
        pass
    _session = None
    return "Disconnected from Chrome CDP (browser window stays open)."
