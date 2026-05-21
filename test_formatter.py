"""Tests for src/formatter.py — zero-dependency."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.formatter import Formatter


def test_noop_on_clean_text():
    fmt = Formatter(enabled=True)
    clean = "Hello! How can I help you today?"
    assert fmt.format(clean) == clean
    print("  clean text unchanged: OK")


def test_disabled():
    fmt = Formatter(enabled=False)
    dirty = "text with \U0001F600 emoji"
    assert fmt.format(dirty) == dirty
    print("  disabled passthrough: OK")


def test_strips_emoji():
    fmt = Formatter(enabled=True)
    result = fmt.format("Hello \U0001F600 world")
    assert "\U0001F600" not in result
    assert "Hello" in result
    assert "world" in result
    print("  emoji stripped: OK")


def test_strips_common_emoji():
    fmt = Formatter(enabled=True)
    result = fmt.format("\u2705 Done!")
    assert result == "Done!"
    print("  checkmark stripped: OK")


def test_strips_zero_width():
    fmt = Formatter(enabled=True)
    result = fmt.format("hello\u200Bworld")
    assert result == "hello world" or result == "helloworld"
    print("  zero-width char stripped: OK")


def test_strips_invisible():
    fmt = Formatter(enabled=True)
    result = fmt.format("text\uFEFFmore")
    assert "\uFEFF" not in result
    print("  BOM stripped: OK")


def test_strips_mcp_tool_call_json():
    fmt = Formatter(enabled=True)
    text = 'Response here. {"name": "tool_x", "parameters": {"a": 1}} trailing'
    result = fmt.format(text)
    assert '"name"' not in result or '"parameters"' not in result
    print("  MCP tool call JSON stripped: OK")


def test_strips_json_fences():
    fmt = Formatter(enabled=True)
    text = "Here is text\n```json\nsome content\n```\nafter"
    result = fmt.format(text)
    assert "```" not in result
    assert "some content" in result
    print("  JSON fences stripped: OK")


def test_strips_json_fences_no_lang():
    fmt = Formatter(enabled=True)
    text = "```\nplain fence\n```"
    result = fmt.format(text)
    assert "```" not in result
    assert "plain fence" in result
    print("  plain fences stripped: OK")


def test_collapses_multi_space():
    fmt = Formatter(enabled=True)
    result = fmt.format("hello   world    !")
    assert result == "hello world !"
    print("  multi-space collapsed: OK")


def test_leading_trailing_whitespace():
    fmt = Formatter(enabled=True)
    result = fmt.format("   hello world   ")
    assert result == "hello world"
    print("  whitespace trimmed: OK")


def test_exception_safety():
    fmt = Formatter(enabled=True)
    # Feed something that might break regex
    result = fmt.format("\0")
    assert isinstance(result, str)
    print("  exception safety: OK")


if __name__ == "__main__":
    test_noop_on_clean_text()
    test_disabled()
    test_strips_emoji()
    test_strips_common_emoji()
    test_strips_zero_width()
    test_strips_invisible()
    test_strips_mcp_tool_call_json()
    test_strips_json_fences()
    test_strips_json_fences_no_lang()
    test_collapses_multi_space()
    test_leading_trailing_whitespace()
    test_exception_safety()
    print()
    print("=" * 50)
    print("All Formatter tests passed.")
