"""Skill: Web search via DuckDuckGo for factual context.

Auto-discovered via @tool() decorator — no manual wiring needed.
"""

from loguru import logger

from src.config import debug_enabled
from .._registry import tool

from pathlib import Path
import tomllib
from langchain_core.messages import AIMessage

_HERE = Path(__file__).parent
_UNAVAILABLE_MSG = "I cannot search the web right now — the web search tool is not enabled."

_try_manifest = _HERE / "manifest.toml"
if _try_manifest.exists():
    try:
        _UNAVAILABLE_MSG = tomllib.loads(_try_manifest.read_text()).get(
            "skill", {}).get("unavailable_message", _UNAVAILABLE_MSG)
    except Exception:
        pass


async def handler(input, config=None):
    """Returned when the skill is disabled — provides a clear unavailable message."""
    return {"messages": [AIMessage(content=_UNAVAILABLE_MSG)]}


def _search_web(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo and return top results as structured text."""
    logger.info("Web search for: {!r}", query)

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        results = list(DDGS().text(query, max_results=max_results))
    except ImportError:
        return (
            "Web search is not available — the ddgs package "
            "is not installed. Run: pip install ddgs"
        )
    except Exception as exc:
        logger.warning("Search failed: {}", exc)
        return f"Search failed: {exc}"

    if not results:
        logger.info("No search results for {!r}", query)
        return f"No results found for '{query}'."

    logger.info("Search returned {} results for {!r}", len(results), query)

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("href", "")
        body = r.get("body", "")[:200]
        lines.append(f"{i}. {title}\n   {url}\n   {body}")

    output = "\n\n".join(lines)

    if debug_enabled():
        logger.debug("Search results for {!r}:\n{}", query, output)

    return output


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
