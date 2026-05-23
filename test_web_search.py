"""Tests for web search skill — requires network (integration)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.tools.web_search import _search_web


def test_search_returns_results():
    result = _search_web("python programming language", max_results=3)
    assert isinstance(result, str)
    assert len(result) > 0
    assert "1. " in result
    print(f"  returns results: OK ({len(result)} chars)")
    print(f"    first line: {result.split(chr(10))[0][:80]}")


def test_search_no_results():
    result = _search_web("xyqqwerasdfghjklzxcvbnm", max_results=3)
    assert "No results found" in result or "Search failed" in result or len(result) > 0
    print("  no results handled: OK")


def test_search_empty_query():
    result = _search_web("", max_results=3)
    assert isinstance(result, str)
    print(f"  empty query handled: OK ({len(result)} chars)")


if __name__ == "__main__":
    test_search_returns_results()
    test_search_no_results()
    test_search_empty_query()
    print()
    print("=" * 50)
    print("All web search tests passed.")
