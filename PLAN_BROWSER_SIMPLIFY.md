# Plan: Simplify Browser Skill — Remove Playwright, Use requests + html2text

Current `browser.py` is 365 lines with 7 tools, half of which require Playwright async CDP to Chromium. The user uses Firefox as their default browser.

**Goal:** Keep 2 simple tools (`open` via D-Bus, `read` via HTTP), remove Playwright entirely.

---

## What changes

| Tool | Before | After |
|------|--------|-------|
| `tool_browser_open(url)` | D-Bus OpenURI | Same (unchanged) |
| `tool_browser_search(query)` | CDP → DuckDuckGo | **Remove** — LLM uses `tool_search_web` from web_search skill |
| `tool_browser_read_page(max_chars)` | CDP → `page.inner_text()` | **Replace** with `requests.get(url)` + `html2text`; takes `url` param |
| `tool_browser_new_tab()` | CDP | **Remove** |
| `tool_browser_close_tab()` | CDP | **Remove** |
| `tool_browser_list_tabs()` | CDP | **Remove** |
| `tool_browser_close_browser()` | CDP disconnect | **Remove** |

Result: ~60-line `browser.py`, zero async, zero subprocess browsers, zero Playwright.

---

## Step-by-step guide

### Step 1 — Add `html2text` and `requests` to requirements.txt

File: `requirements.txt`

- Add `html2text>=2024.2` (pure Python, converts HTML to readable Markdown text)
- Add `requests>=2.32` (already a transitive dependency, make it explicit)
- Remove `playwright>=1.50`

After edit, install:
```
pip install html2text requests
```

### Step 2 — Rewrite `src/tools/browser.py`

Delete entire file content (365 lines). Replace with ~60 lines:

```python
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
    except Exception as exc:
        return f"Failed to open {url}: {exc}"


def _fetch_page(url: str, max_chars: int = 4000) -> str:
    """Fetch and extract readable text from a web page via HTTP."""
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
```

**What's removed:**
- All `async/await` — no more Playwright
- `_BrowserSession`, `_connect_cdp()`, `_get_page()`, `_navigate()`, `_read_text()`, `_refresh_pages()`
- Import of `browser_cdp_port`, `playwright.async_api`, `async_playwright`
- 5 CDP-dependent tools (search, new_tab, close_tab, list_tabs, close_browser)

**What's new:**
- `html2text` + `requests` imports
- `_fetch_page(url, max_chars)` — synchronous HTTP fetch + HTML-to-text conversion
- `tool_browser_read(url, max_chars)` — takes a URL parameter (was implicit "current tab")

### Step 3 — Update `src/tools/browser.toml`

Replace the entire file content:

```toml
[skill]
name = "browser"
description = "Open URLs in system browser and read web page content"
prompt_hint = "- Open URLs in the user's default browser. Read page content via HTTP (no browser tab required)."
```

### Step 4 — Update `prompts/general.md`

Replace the browser-related lines (currently lines 18-20):

Change from:
```
- Use the browser only when the user explicitly asks you to open a website, interact with web content, or show something in a browser. For simple factual lookups, prefer the web_search tool instead.
- NEVER close the browser unless the user explicitly asks you to close it. Leave the browser open after opening a page or tab.
- The browser_open tool opens URLs in the user's system browser. To read page content or manage tabs, Chromium will be auto-launched if needed (sudo pacman -S chromium).
```

To:
```
- Use the browser only when the user explicitly asks you to open a website, or read a page. For factual lookups, prefer the web_search tool instead.
- The browser_open tool opens URLs in your system browser via the desktop portal.
- The browser_read tool fetches and extracts text from a URL via HTTP — no browser tab needed.
```

### Step 5 — Remove `cdp_port` from config

**File: `config.json`** — in the `"browser"` section, remove the line:
```json
"cdp_port": 9222
```

Full browser section becomes:
```json
"browser": {
    "headless": false,
    "engine": "chromium"
}
```

Wait — `headless` and `engine` are now unused too. Remove the entire `"browser"` section from `config.json` unless the user wants to keep it for future use. For now, **keep a minimal section:**

```json
"browser": {}
```

Actually, since no code reads `headless` or `engine` anymore, and `cdp_port` is gone, we can remove the entire `"browser"` key from `config.json` entirely. But that might cause `config.py` errors. Let's do it properly:

**Remove the `"browser"` key from `config.json`:**

```jsonc
// Before (lines 27-31):
    "browser": {
        "headless": false,
        "engine": "chromium",
        "cdp_port": 9222
    },

// After: delete these 4 lines. Keep json valid.
```

**File: `src/config.py`** — remove `browser_cdp_port()`, `browser_headless()`, `browser_engine()`:

1. In `DEFAULT_CONFIG` dict (around line 18), remove the `"browser": {...}` entry.
2. Remove the three accessor functions (around lines 150-165):
   - `def browser_headless()`
   - `def browser_engine()`
   - `def browser_cdp_port()`

### Step 6 — Update `test_browser.py`

Current test file tests `tool_browser_open`, CDP connect, search, and list_tabs.

Rewrite with:
1. **test_dbus_open** — `tool_browser_open("https://example.com")` → expect "Opened" in result
2. **test_read_page** — `tool_browser_read("https://example.com")` → expect >100 chars of readable content
3. **test_read_bad_url** — `tool_browser_read("http://this-domain-does-not-exist.invalid")` → expect "Failed" in result
4. **test_read_non_html** — optional, `tool_browser_read("https://httpbin.org/image/png")` → expect non-HTML message

Remove:
- `async def test_cdp_connect_error()`
- `async def test_search_needs_cdp()`
- `async def test_tabs_needs_cdp()`
- All `asyncio.run()` wrappers
- Import of `_connect_cdp`, `tool_browser_search`, `tool_browser_list_tabs`

The new tests are all synchronous — no `asyncio`, no `async/await`.

### Step 7 — Update `README.md`

In the config table (around line 186), remove:
```
| browser.cdp_port | int | 9222 | Chrome DevTools Protocol port for browser control |
```

Also add `html2text` to the dependencies if there's a list.

### Step 8 — Remove Playwright browser binary (optional cleanup)

```
playwright uninstall chromium
```

This frees ~200 MB disk space. Do this after Step 2 (after removing `playwright` from requirements).

### Step 9 — Verify

```bash
# Compile check
python3 -c "import compileall; compileall.compile_dir('src', quiet=1, force=True); print('OK')"

# Browser skill tests
python3 test_browser.py

# Full unit + integration suite
python3 run_tests.py --unit
python3 run_tests.py --integration --timeout 180
```

---

## Files touched (summary)

| File | Action | Lines changed |
|------|--------|---------------|
| `requirements.txt` | +2 lines, -1 line | 3 |
| `src/tools/browser.py` | Full rewrite (365 → ~60) | ~305 |
| `src/tools/browser.toml` | 3 lines replaced | 3 |
| `prompts/general.md` | 6 lines replaced | 6 |
| `config.json` | Remove `browser` section | 4 |
| `src/config.py` | Remove 3 functions + default entry | ~15 |
| `test_browser.py` | Full rewrite (async→sync, 4 tests) | ~50 |
| `README.md` | Remove cdp_port row | 1 |

**Total:** 8 files, ~387 lines removed.
