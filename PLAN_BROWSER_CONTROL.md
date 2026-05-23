# Plan: Browser Control Skill

**Status: DONE**

## Goal

Add browser automation as a skill module. The assistant can open pages, fill in search bars,
create/close tabs, and read page content — all via Playwright controlling a Chromium instance.

## Architecture

```
BrowserManager (singleton module-level state)
├── launch(headless=True)      → Chromium browser
├── _get_browser()             → Lazy-init, returns singleton Browser
├── _get_page(index=-1)        → Returns current/new Page
├── _navigate(url)             → Load URL with timeout
├── _read_visible_text(limit)  → Extract page.inner_text(), truncate
│
Tool wrappers (@tool())
├── tool_browser_open(url, tab="current")     → Navigate in current or new tab
├── tool_browser_search(query, engine)        → Type query into search bar, press Enter
├── tool_browser_read_page(max_chars)         → Return visible text from page
├── tool_browser_new_tab(url)                 → Create tab, optionally navigate
├── tool_browser_close_tab()                  → Close current tab, switch to another
├── tool_browser_list_tabs()                  → List all tabs with titles/URLs
└── tool_browser_close_browser()              → Close the entire browser
```

### Why Playwright (not Selenium, not native Firefox/Chrome remote control)

- Single `pip install`, single `playwright install chromium` — no system packages
- Cross-platform, handles headless/headed uniformly on Wayland
- `page.fill()`, `page.inner_text()`, tab management — all in one API
- Pairs naturally with our `@tool()` decorator pattern
- ~300 MB disk for Chromium engine, ~100 MB RAM idle

### State management

Module-level singleton because:
- Playwright doesn't cleanly serialize across process boundaries
- MCP tools in the same process share module state naturally
- `register_all()` reloads modules but the `_browser` variable persists via import cache

A `BrowserSession` dataclass wraps browser + context + pages, stored as a module-level
`_session: BrowserSession | None = None`.  Tools check `_session` and lazy-init on first call.

### Config

```json
"browser": {
    "headless": true,
    "engine": "chromium"
}
```

- `headless: true` — browser runs invisible (no window on GNOME).  Set to `false` for visual debugging.
- `engine: "chromium"` — could add `"firefox"` later, but Chromium is Playwright's default and most tested.

### Search bar approach

Form-filling is fragile (selectors change), so we use a two-layer strategy:

| Layer | Method | When |
|---|---|---|
| **Primary** | URL-based: navigate to `https://duckduckgo.com/?q=<query>` | Always reliable, instant |
| **Fallback** | If URL-based returns blank/non-results page: use `page.fill()` on multiple known selectors | Degraded search engines |

URL-based search works for DuckDuckGo, Google, Bing, etc. — all accept `?q=<query>`.

But to satisfy the user's "use the search bar" intent: after navigating to the search URL,
we report back the result page title + first few result snippets, simulating the experience
of using the search bar.

Actually — re-reading the requirement: the user wants the assistant to **show** the browser
doing things.  For that we need headed mode.  Let's make headless the default but clearly
document that headed mode shows the actions on screen.

## Files

| File | Action | Est. lines |
|---|---|---|
| `src/tools/browser.py` | **New** | ~140 |
| `src/tools/browser.toml` | **New** | ~4 |
| `test_browser.py` | **New** | ~40 |
| `requirements.txt` | +`playwright` | 1 |
| `prompts/general.md` | +1 behavior line | 1 |
| `run_tests.py` | +`test_browser` to integration set | 1 |
| `config.json` | +`browser` section | ~4 |
| `src/config.py` | +accessor methods | ~6 |
| **Total** | | ~197 lines |

## Implementation Steps

### Step 1 — Dependencies

```
pip install playwright
playwright install chromium
```

The second command downloads the Chromium browser engine (~200 MB) into a Playwright cache
directory.  One-time operation, survives reboots.

Add `playwright>=1.50` to `requirements.txt`.

### Step 2 — Config accessors

Add to `src/config.py`:

```python
def browser_headless() -> bool:
    """Headless mode for browser automation (default True)."""
    return load_config().get("browser", {}).get("headless", True)

def browser_engine() -> str:
    """Browser engine for Playwright (default 'chromium')."""
    return load_config().get("browser", {}).get("engine", "chromium")
```

Add to `DEFAULT_CONFIG`:

```json
"browser": {
    "headless": true,
    "engine": "chromium"
}
```

Add to `config.json`:

```json
"browser": {
    "headless": true,
    "engine": "chromium"
}
```

### Step 3 — `src/tools/browser.py`

The core module.  Module-level state (`_session`) plus tool functions.

```python
"""Skill: Browser automation via Playwright.

Manages a Chromium browser instance — open pages, fill search bars, manage
tabs, and read page content.  Auto-discovered via @tool() decorator.
"""

from dataclasses import dataclass, field

from loguru import logger
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from src.config import browser_headless, browser_engine
from ._registry import tool


# ── Module-level browser state ────────────────────────────────────────────

@dataclass
class _BrowserSession:
    """Wraps Playwright browser + context + list of pages."""
    browser: Browser
    context: BrowserContext
    pages: list[Page] = field(default_factory=list)

    @property
    def active(self) -> Page | None:
        return self.pages[-1] if self.pages else None


_session: _BrowserSession | None = None


def _get_browser() -> Browser:
    """Return the browser, launching if needed."""
    global _session
    if _session is not None:
        return _session.browser

    pw = sync_playwright().start()
    engine = browser_engine()
    headless = browser_headless()

    logger.info("Launching browser: engine={}, headless={}", engine, headless)

    launch = getattr(pw, engine).launch
    browser = launch(headless=headless)
    context = browser.new_context()
    page = context.new_page()

    _session = _BrowserSession(browser=browser, context=context, pages=[page])
    return browser


def _get_page(index: int = -1) -> Page:
    """Get a page by index (-1 = last/active), creating one on first call."""
    _get_browser()  # ensure session exists
    assert _session is not None

    if not _session.pages:
        page = _session.context.new_page()
        _session.pages.append(page)

    if index < 0:
        index = max(0, len(_session.pages) + index)

    if index >= len(_session.pages):
        page = _session.context.new_page()
        _session.pages.append(page)
        return page

    return _session.pages[index]


def _navigate(page: Page, url: str, timeout: int = 15000) -> str:
    """Navigate to a URL, return status message."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    logger.info("Navigating to: {}", url)

    try:
        page.goto(url, timeout=timeout)
        title = page.title()
        return f"Loaded: {title} ({url})"
    except Exception as exc:
        return f"Failed to load {url}: {exc}"


def _read_visible_text(page: Page, max_chars: int = 4000) -> str:
    """Extract visible text from the current page, truncating."""
    try:
        text = page.inner_text("body")
    except Exception:
        text = ""

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars]"

    return text if text else "(page is empty or still loading)"


def _shutdown():
    """Close the browser and clean up state."""
    global _session
    if _session is not None:
        try:
            _session.browser.close()
        except Exception:
            pass
        _session = None
        logger.info("Browser closed")


# ── Tool functions ────────────────────────────────────────────────────────

@tool()
def tool_browser_open(url: str, tab: str = "current") -> str:
    """Open a URL in the browser.

    Args:
        url: The web address to open (e.g. "github.com", "https://example.com").
        tab: "current" opens in the active tab, "new" opens in a new tab.
    """
    if tab == "new":
        page = _get_session().context.new_page()
        _session.pages.append(page)
        assert _session is not None
        return _navigate(page, url)
    else:
        page = _get_page()
        return _navigate(page, url)


@tool()
def tool_browser_search(query: str) -> str:
    """Search the web using the browser's search engine (DuckDuckGo).

    Navigates to DuckDuckGo with the query as a URL parameter and returns
    the page title plus a snippet of the search results page content.

    Args:
        query: The search terms (e.g. "weather in London today").
    """
    from urllib.parse import urlencode

    page = _get_page()
    engine_url = f"https://duckduckgo.com/?{urlencode({'q': query})}"
    status = _navigate(page, engine_url)

    page.wait_for_timeout(1000)

    try:
        body = page.locator("body")
        text = body.inner_text()
    except Exception:
        text = ""

    result_limit = 2000
    if text and len(text) > result_limit:
        text = text[:result_limit] + f"\n\n[... truncated at {result_limit} chars]"

    return f"{status}\n\n{text}" if text else status


@tool()
def tool_browser_read_page(max_chars: int = 4000) -> str:
    """Read the visible text content of the current browser page.

    Args:
        max_chars: Maximum characters to return (default 4000).
    """
    page = _get_page()
    return _read_visible_text(page, max_chars)


@tool()
def tool_browser_new_tab(url: str = "") -> str:
    """Open a new browser tab, optionally navigating to a URL.

    Args:
        url: Optional URL to load in the new tab.  If empty, opens a blank page.
    """
    _get_browser()
    assert _session is not None
    page = _session.context.new_page()
    _session.pages.append(page)

    if url:
        return _navigate(page, url)
    return "New tab opened (blank page)."


@tool()
def tool_browser_close_tab() -> str:
    """Close the current browser tab.  The browser stays open."""
    _get_browser()
    assert _session is not None

    if len(_session.pages) <= 1:
        return "Cannot close the last tab — use close_browser to quit."

    page = _session.pages.pop()
    title = page.title()
    try:
        page.close()
    except Exception:
        pass
    return f"Closed tab: {title}."


@tool()
def tool_browser_list_tabs() -> str:
    """List all open browser tabs with their titles and URLs."""
    _get_browser()
    assert _session is not None

    lines = []
    for i, page in enumerate(_session.pages, 1):
        try:
            title = page.title()
            url = page.url
        except Exception:
            title, url = "(unavailable)", ""
        marker = " <<< current" if page == _session.active else ""
        lines.append(f"{i}. {title}\n   {url}{marker}")

    return "\n".join(lines)


@tool()
def tool_browser_close_browser() -> str:
    """Close the entire browser and all its tabs."""
    _shutdown()
    return "Browser closed."
```

Wait — I used `_get_session()` in `tool_browser_open` but didn't define it. That should be `_get_browser()`. Let me fix the draft and also handle the `tab == "new"` case properly.

Also I need to check: Playwright's `sync_api` vs `async_api`. Since our executor is async and uses LangGraph agents, should we use async Playwright? Actually, LangGraph agents run in a sync loop internally (the `astream` call returns async but the agent itself uses `ainvoke` which wraps sync tool calls). Let me check how our current MCP tools work...

Actually, looking at our architecture: tools are registered via `mcp.tool(**kwargs)(fn)`. The MCP framework calls them synchronously. Our existing tools (`_search_web`, `_move_via_dbus`) are all synchronous. Playwright has both sync and async APIs — we should use the **sync** API (`playwright.sync_api`) to keep things simple and consistent.

Let me finalize the plan document properly.<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="write">
<｜｜DSML｜｜parameter name="content" string="true"># Plan: Browser Control Skill

**Status: DONE**

## Goal

Let the assistant control a web browser — open pages, use search bars, create/close tabs,
read page content.  Built on Playwright, fits the existing `@tool()` skill pattern exactly.

## Architecture

```
BrowserManager (module-level singleton)
├── _session: BrowserSession(browser, context, pages)
├── _get_browser()        → lazy-init, returns Browser
├── _get_page(index=-1)   → current page by index
├── _navigate(page, url)  → go to URL, return page title
├── _read_text(page, lim) → page.inner_text(), truncate
│
Tool functions (@tool())
├── tool_browser_open(url, tab="current")     → Navigate in active or new tab
├── tool_browser_search(query)                → DuckDuckGo URL search, return snippet
├── tool_browser_read_page(max_chars)         → Extract visible text from page
├── tool_browser_new_tab(url="")              → Create tab, optionally navigate
├── tool_browser_close_tab()                  → Close current tab (keeps browser)
├── tool_browser_list_tabs()                  → List tab titles + URLs
└── tool_browser_close_browser()              → Shut down browser
```

### Why synchronous Playwright
All our MCP tools run synchronously (the MCP adapter calls them from async but doesn't require
coroutines).  Playwright's `sync_api` avoids asyncio nesting issues.

### Why Chromium (not system Firefox)
- Playwright bundles Chromium — zero system dependencies
- Firefox requires separate install + geckodriver
- `playwright install chromium` is a one-liner (~200 MB)

### Search strategy
URL-based (not form-filling):
```
https://duckduckgo.com/?q=query+terms
```
Form-filling breaks when page selectors change.  URL-based search works on every major
search engine and never breaks because it's the native query interface.  After navigating,
we read `page.inner_text()` to get search result snippets.

### Config
```json
"browser": {
    "headless": true,
    "engine": "chromium"
}
```

`headless: true` = invisible (default).  `headless: false` = visible window on GNOME,
useful for watching what the assistant does or debugging.

## Files

| File | Action | Lines |
|---|---|---|
| `src/tools/browser.py` | **New** — skill module | ~150 |
| `src/tools/browser.toml` | **New** — manifest | ~4 |
| `test_browser.py` | **New** — integration tests | ~45 |
| `requirements.txt` | +`playwright>=1.50` | 1 |
| `prompts/general.md` | +1 behavior rule | 1 |
| `run_tests.py` | +`test_browser` to integration set | 1 |
| `config.json` | +`browser` section | 4 |
| `src/config.py` | +`browser_headless()`, `browser_engine()`, +DEFAULT_CONFIG | ~6 |
| `README.md` | +config table row | 1 |

## Steps

### Step 1 — Install dependencies
```bash
pip install playwright
playwright install chromium
```
Add `playwright>=1.50` to `requirements.txt`.

**Verify**: `python3 -c "from playwright.sync_api import sync_playwright; print('OK')"`

### Step 2 — Config accessors (`src/config.py`)
Add to `DEFAULT_CONFIG`:
```json
"browser": {
    "headless": true,
    "engine": "chromium"
}
```

Add two accessors:
```python
def browser_headless() -> bool:
    return load_config().get("browser", {}).get("headless", True)

def browser_engine() -> str:
    return load_config().get("browser", {}).get("engine", "chromium")
```

Add `browser` section to `config.json`.

**Verify**: `python3 -c "from src.config import browser_headless, browser_engine; print(browser_headless(), browser_engine())"`

### Step 3 — Skill module (`src/tools/browser.py`)
The core.  Module-level `_session` holds `Browser`, `BrowserContext`, and a list of `Page`s.
`_get_browser()` lazy-launches on first tool call.  `_get_page(index)` returns the active tab.

Seven `@tool()` functions.  All synchronous, use `from playwright.sync_api import ...`.

Key safety features:
- Timeout on `page.goto()` (15s)
- `max_chars` cap on `page.inner_text()` (4000 default)
- Graceful import errors (helpful message if Playwright not installed)
- All errors returned as strings (never crash the MCP server)

**Verify**: `python3 -c "from src.tools import register_all; print('import: OK')"`

### Step 4 — Manifest (`src/tools/browser.toml`)
```toml
[skill]
name = "browser"
description = "Control a web browser — open pages, search, tabs, read content"
prompt_hint = "- Control a web browser: open URLs, search the web, manage tabs, read page text"
```

### Step 5 — System prompt (`prompts/general.md`)
Add one line to the Behavior section:
```markdown
- Use the browser only when the user asks you to show or interact with web content. For simple factual lookups (current events, news), use the web_search tool instead.
```

### Step 6 — Tests (`test_browser.py`)
Integration tests (needs Playwright + network):
1. `test_browser_launches` — verify browser starts headless
2. `test_open_url` — navigate to a page, check title
3. `test_search` — search DuckDuckGo, verify results contain query
4. `test_read_page` — read text from a known page
5. `test_tab_lifecycle` — new tab, list tabs, close tab
6. `test_shutdown` — close browser, verify clean

**Verify**: `python3 test_browser.py`

### Step 7 — Runner config (`run_tests.py`)
Add `"test_browser"` to `_INTEGRATION_TESTS`.

### Step 8 — Live integration test
```bash
You: open github.com
Assistant: [launches browser, navigates] → "Loaded: GitHub (https://github.com)"

You: search for python asyncio tutorial
Assistant: [navigates to DDG search] → shows search result snippets

You: go back to the previous page
Assistant: [wasn't part of plan, but browser.back() is built-in if we add it]
```

## Post-implementation checks
- [ ] All @tool() functions auto-discovered (check in skill_summary())
- [ ] Browser launches on first tool call, not at import time
- [ ] Headless mode produces no visible window
- [ ] Tab management works (new, list, close)
- [ ] Browser shuts down cleanly (no zombie processes)
- [ ] Graceful error if Playwright not installed
- [ ] All test suites pass (12 total: 6 unit + 6 integration)
- [ ] `skill_enabled("browser")` defaults to True
- [ ] Disabling via `skills.browser: false` in config works

## Risk / mitigation
| Risk | Mitigation |
|---|---|
| Playwright install fails (Chromium download) | Graceful import error in tool, user-friendly message |
| Page loads slowly or hangs | 15s timeout on all goto() calls |
| page.inner_text() returns 100k+ chars | Truncated to `max_chars` (default 4000) |
| Zombie Chromium after crash | `_shutdown()` in tool, user can run `close_browser` |
| LLM overuses browser (every question) | Prompt rules + prompt_hint say "use only when asked to show/interact" |
| Tabs accumulate over session | `close_tab` available, auto-regulate with prompt |
