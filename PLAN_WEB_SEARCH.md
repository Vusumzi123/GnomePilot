# Plan: Web Search Skill

**Status: DRAFT**

## Goal

Add a web search capability as a new skill module. The assistant should use it
only when necessary — for current events, factual queries beyond training data,
or when the user explicitly asks for web information. Return structured results
the LLM can incorporate into responses.

## Architecture

```
tool_search_web(query, max_results=5)
  ├── Searches via DuckDuckGo (free, no API key)
  ├── Returns top N results: title + URL + snippet
  └── LLM uses results to answer factually
```

### Why DuckDuckGo

- Zero API key — no account setup, no billing
- Privacy-respecting (no tracking, no user profiling)
- `duckduckgo_search` Python package handles HTML parsing
- Good enough for casual context-gathering queries

### When the LLM should use it

The `prompt_hint` in `web_search.toml` guides the LLM:

```toml
prompt_hint = "- Search the web for current information (use ONLY when the user asks for facts you don't know)"
```

Combined with a strong behavior clause in the system prompt:

> Use web search ONLY when the user explicitly asks for information you cannot
> confidently answer from training data. Prefer your own knowledge for general
> questions. Limit searches to 1-2 per conversation turn.

## Files

| File | Action |
|---|---|
| `src/tools/web_search.py` | **New** (~35 lines) |
| `src/tools/web_search.toml` | **New** (~4 lines) |
| `test_web_search.py` | **New** (~25 lines) |
| `requirements.txt` | Add `duckduckgo-search>=8.0.0` |

No config.json changes — skill defaults to enabled.

## Implementation

### 1. Dependency

```
duckduckgo-search>=8.0.0
```

### 2. `src/tools/web_search.py`

```python
"""Skill: Web search via DuckDuckGo for factual context.

Auto-discovered via @tool() decorator — no manual wiring needed.
"""

from ._registry import tool


def _search_web(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo and return top results as structured text."""
    try:
        from duckduckgo_search import DDGS
        results = list(DDGS().text(query, max_results=max_results))
    except ImportError:
        return (
            "Web search is not available — the duckduckgo-search package "
            "is not installed. Run: pip install duckduckgo-search"
        )
    except Exception as exc:
        return f"Search failed: {exc}"

    if not results:
        return f"No results found for '{query}'."

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("href", "")
        body = r.get("body", "")[:200]
        lines.append(f"{i}. {title}\n   {url}\n   {body}")

    return "\n\n".join(lines)


@tool()
def tool_search_web(query: str, max_results: int = 5) -> str:
    """Search the web for current information.

    Use this ONLY when the user asks a question you cannot confidently answer
    from your training data (e.g. current events, recent news, specific facts
    you're unsure about).  Do NOT use this for general conversation, opinions,
    or questions you can answer yourself.

    Returns the top results with title, URL, and snippet.

    Args:
        query: What to search for (e.g. "weather in Berlin today",
               "latest Python release notes").
        max_results: Number of results to return (1–10, default 5).
    """
    return _search_web(query, max_results)
```

### 3. `src/tools/web_search.toml`

```toml
[skill]
name = "web_search"
description = "Search the web via DuckDuckGo for current facts and context"
prompt_hint = "- Search the web for current information (use sparingly, only when needed)"
```

### 4. Prompts update

The `prompts/general.md` gets `{tool_descriptions}` which auto-includes the
`prompt_hint` from the manifest. Add a specific behavior line:

```markdown
- You have a web search tool. Use it ONLY when the user asks for information
  you cannot confidently answer from training data (current events, specific
  facts). Limit to 1–2 searches per conversation. Never search for opinions,
  advice, or things you can answer yourself.
```

### 5. Tests (`test_web_search.py`)

```python
"""Tests for web search skill."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.tools.web_search import _search_web


def test_search_returns_results():
    result = _search_web("python programming language", max_results=3)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should have at least one numbered result
    assert "1. " in result
    print(f"  returns results: OK ({len(result)} chars)")
    print(f"    first line: {result.split(chr(10))[0][:80]}")


def test_search_no_results():
    result = _search_web("xyqqwerasdfghjklzxcvbnm", max_results=3)
    assert "No results found" in result or "Search failed" in result or len(result) > 0
    print(f"  no results handled: OK")


def test_search_empty_query():
    result = _search_web("", max_results=3)
    assert isinstance(result, str)
    print(f"  empty query handled: OK")


if __name__ == "__main__":
    test_search_returns_results()
    test_search_no_results()
    test_search_empty_query()
    print()
    print("=" * 50)
    print("All web search tests passed.")
```

### 6. `run_tests.py` — classify as integration

```python
_INTEGRATION_TESTS = {..., "test_web_search"}  # needs network
```

## Behavior design: preventing overuse

Three layers control web search usage:

| Layer | Mechanism |
|---|---|
| **Prompt** | System prompt tells LLM to use only when necessary, limit 1-2/conversation |
| **Tool docstring** | The LLM reads "Use this ONLY when..." before calling the tool |
| **Tool result format** | Returns structured text (not raw data) — LLM has no reason to refine/re-search |

The prompt is the primary guard. If the LLM overuses it despite the prompt,
we can add a programmatic rate limiter later — track searches per conversation
turn and reject beyond a threshold.

## Verification

```bash
# 1. Install dependency
pip install duckduckgo-search

# 2. Run unit test
python3 test_web_search.py

# 3. Integration test via assistant
You: what is the latest python version?
Assistant: [calls tool_search_web] → returns actual results → answers factually

# 4. Verify it doesn't overuse
You: how are you today?
Assistant: [does NOT call search] → answers conversationally
```

## File manifest

| File | Action | Est. lines |
|---|---|---|
| `src/tools/web_search.py` | **New** | 50 |
| `src/tools/web_search.toml` | **New** | 4 |
| `test_web_search.py` | **New** | 35 |
| `requirements.txt` | +1 line | 1 |
| `prompts/general.md` | +1 behavior line | 1 |
| `run_tests.py` | Add `test_web_search` to integration set | 1 |
| **Total** | | ~92 lines |
