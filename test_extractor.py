"""Tests for src/extractor.py — zero-dependency (no Ollama needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.extractor import Extractor
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


def _make_ai(text: str, tool_calls=None):
    return AIMessage(content=text, tool_calls=tool_calls or [])


def _make_tool(content, name="tool_x"):
    return ToolMessage(content=content, name=name, tool_call_id="tc_1")


def test_response_from_ai():
    msgs = [
        HumanMessage(content="hello"),
        _make_ai("Hi there! How can I help?"),
    ]
    assert Extractor.response(msgs) == "Hi there! How can I help?"
    print("  response from AIMessage: OK")


def test_response_skips_ai_with_tool_calls():
    tool_call = {"name": "tool_open_application", "args": {"app_name": "firefox"}, "id": "1"}
    msgs = [
        HumanMessage(content="open firefox"),
        _make_ai("", tool_calls=[tool_call]),
        _make_ai("Opened Firefox.", tool_calls=[]),
    ]
    assert Extractor.response(msgs) == "Opened Firefox."
    print("  response skips tool-call AIMessages: OK")


def test_response_skips_malformed_json():
    # Sometimes the LLM outputs JSON-like strings as text
    msgs = [
        HumanMessage(content="hello"),
        _make_ai('{"name": "some_tool", "parameters": {"x": 1}}', tool_calls=[]),
        _make_ai("Real response here.", tool_calls=[]),
    ]
    assert Extractor.response(msgs) == "Real response here."
    print("  response skips malformed JSON: OK")


def test_response_fallback_to_tool_message():
    msgs = [
        HumanMessage(content="open firefox"),
        _make_ai("", tool_calls=[{"name": "t", "args": {}, "id": "1"}]),
        _make_tool("Opened Firefox."),
    ]
    assert Extractor.response(msgs) == "Opened Firefox."
    print("  response falls back to ToolMessage: OK")


def test_response_fallback_last_message():
    msgs = [HumanMessage(content="hello")]
    # No AI response at all — should return the human message content
    result = Extractor.response(msgs)
    assert result == "hello"
    print("  response falls back to last message: OK")


def test_tool_calls_basic():
    msgs = [
        HumanMessage(content="open firefox"),
        _make_ai("", tool_calls=[{
            "name": "tool_open_application",
            "args": {"app_name": "firefox"},
            "id": "tc_1",
        }]),
        _make_tool("Opened Firefox.", name="tool_open_application"),
    ]
    calls = Extractor.tool_calls(msgs)
    assert len(calls) == 1
    assert calls[0]["name"] == "tool_open_application"
    assert calls[0]["args"] == {"app_name": "firefox"}
    assert calls[0]["result"] == "Opened Firefox."
    print("  tool_calls basic: OK")


def test_tool_calls_multiple():
    msgs = [
        HumanMessage(content="search htop"),
        _make_ai("", tool_calls=[
            {"name": "tool_search_packages", "args": {"query": "htop"}, "id": "tc_1"},
        ]),
        _make_tool("Found htop in official repos.", name="tool_search_packages"),
        _make_ai("", tool_calls=[
            {"name": "tool_install_package", "args": {"package_name": "htop"}, "id": "tc_2"},
        ]),
        _make_tool("Successfully installed htop.", name="tool_install_package"),
    ]
    calls = Extractor.tool_calls(msgs)
    assert len(calls) == 2
    assert calls[0]["name"] == "tool_search_packages"
    assert calls[1]["name"] == "tool_install_package"
    assert calls[0]["result"] == "Found htop in official repos."
    assert calls[1]["result"] == "Successfully installed htop."
    print("  tool_calls multiple: OK")


def test_tool_calls_no_tools():
    msgs = [
        HumanMessage(content="hello"),
        _make_ai("Hi there!"),
    ]
    calls = Extractor.tool_calls(msgs)
    assert calls == []
    print("  tool_calls empty: OK")


def test_clean_result_list():
    result = [{"type": "text", "text": "Opened Firefox."}]
    assert Extractor.clean_result(result) == "Opened Firefox."
    print("  clean_result list: OK")


def test_clean_result_list_multiple():
    result = [
        {"type": "text", "text": "Part 1."},
        {"type": "text", "text": "Part 2."},
    ]
    assert Extractor.clean_result(result) == "Part 1. Part 2."
    print("  clean_result multi-list: OK")


def test_clean_result_string():
    result = "{'type': 'text', 'text': 'Found htop.'}"
    cleaned = Extractor.clean_result(result)
    assert "htop" in cleaned
    print("  clean_result string: OK")


def test_empty_messages():
    assert Extractor.response([]) == ""
    assert Extractor.tool_calls([]) == []
    print("  empty messages: OK")


if __name__ == "__main__":
    test_response_from_ai()
    test_response_skips_ai_with_tool_calls()
    test_response_skips_malformed_json()
    test_response_fallback_to_tool_message()
    test_response_fallback_last_message()
    test_tool_calls_basic()
    test_tool_calls_multiple()
    test_tool_calls_no_tools()
    test_clean_result_list()
    test_clean_result_list_multiple()
    test_clean_result_string()
    test_empty_messages()
    print()
    print("=" * 50)
    print("All Extractor tests passed.")
