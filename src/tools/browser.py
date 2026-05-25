"""Skill: Browser — open URLs in system browser, read web page content."""

from urllib.parse import urlencode

import dbus
import html2text
import requests
from langchain.tools import tool
from loguru import logger

from src.config import debug_enabled

_session_ua = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


def _dbus_open_url(url: str) -> str:
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
    except Exception as exc:
        return f"Failed to open {url}: {exc}"


def _fetch_page(url: str, max_chars: int = 4000) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    logger.info("Fetch page: {}", url)
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _session_ua},
            timeout=15,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return f"Failed to fetch {url}: {exc}"

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        snippet = resp.text[:500] if resp.text else "(binary content)"
        return f"Not an HTML page. Content-Type: {content_type}\n\n{snippet}"

    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0

    text = converter.handle(resp.text)

    if not text.strip():
        return "(page returned empty content)"

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars]"

    if debug_enabled():
        logger.debug("Fetched {} chars from {}", len(text), url)

    return text


@tool()
def tool_browser_open(url: str) -> str:
    """Open a URL in your default web browser.

    Uses the desktop portal to open in your real browser window.

    Args:
        url: The web address to open (e.g. "github.com", "https://example.com").
    """
    logger.info("Browser open: url={!r}", url)
    return _dbus_open_url(url)


@tool()
def tool_browser_read(url: str, max_chars: int = 4000) -> str:
    """Read the text content of a web page at the given URL.

    Fetches via HTTP and extracts readable text — no browser needed.

    Args:
        url: The web address to read (e.g. "https://en.wikipedia.org/wiki/Linux").
        max_chars: Maximum characters to return (default 4000, max 20000).
    """
    logger.info("Browser read: url={!r}, max_chars={}", url, max_chars)
    return _fetch_page(url, min(max_chars, 20000))
