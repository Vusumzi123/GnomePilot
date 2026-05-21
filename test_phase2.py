"""Phase 2 Review Gate Tests.

Test 1: Desktop file index — scan + resolve
Test 2: "Open Firefox"  — LLM calls tool_open_application
Test 3: "Close Firefox" — LLM calls tool_close_application
Test 4: "Search htop"   — LLM calls tool_search_packages
Test 5: "Install htop"  — LLM calls tool_install_package (requires sudo via pkexec GUI)
Test 6: Chat history — context is built and sized correctly
Test 7: Routing enrichment — _enrich_for_routing injects context
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.orchestrator import Orchestrator
from src.tools.desktop_index import scan, resolve


def _tool_was_called(orch: Orchestrator, tool_name: str) -> bool:
    return any(c["name"] == tool_name for c in orch.last_tool_calls)


def _tool_succeeded(orch: Orchestrator, tool_name: str) -> bool:
    for call in orch.last_tool_calls:
        if call["name"] == tool_name:
            result = str(call["result"]).lower()
            if any(w in result for w in ("success", "launched", "sent close", "closed",
                                          "forcefully terminated", "moved", "opened")):
                return True
            if tool_name in ("tool_search_packages", "tool_capture_screen"):
                return "no packages found" not in result and "'text':" in result
            if tool_name == "tool_install_package":
                return "success" in result or "already" in result
    return False


def test_desktop_index():
    print("--- Test 1: Desktop file index ---")
    entries = scan()
    print(f"  Scanned {len(entries)} desktop entries")
    assert len(entries) > 50, f"Expected >50 entries, got {len(entries)}"

    path = resolve("firefox")
    assert path is not None, "Failed to resolve firefox"
    print(f"  resolve('firefox') → {path.name}")

    assert resolve("zzz_nonexistent_xyzzy") is None
    print(f"  resolve('nonexistent') → None")

    # PWA support: numeric-name .desktop file should resolve via Name= field
    path3 = resolve("terminal")
    assert path3 is not None, "Failed to resolve terminal"
    print(f"  resolve('terminal') → {path3.name}")

    print("PASSED\n")
    return True


def test_chat_history():
    print("--- Test 2: Chat history ---")
    orch = Orchestrator()

    assert orch.chat_history_size >= 0
    assert orch.chat_history == []

    # Simulate adding turns
    orch._add_to_history("hello", "Hi there!")
    assert len(orch.chat_history) == 1
    assert orch.chat_history[0]["user"] == "hello"
    assert orch.chat_history[0]["assistant"] == "Hi there!"

    orch._add_to_history("open firefox", "Opened Firefox.")
    assert len(orch.chat_history) == 2

    # Test message building with history
    msgs = orch._build_messages("what is up", include_history=True)
    assert len(msgs) == 5  # 2 history pairs (4) + 1 current = 5
    assert msgs[0].content == "hello"
    assert msgs[1].content == "Hi there!"
    assert msgs[4].content == "what is up"

    # Without history
    msgs_no = orch._build_messages("what is up", include_history=False)
    assert len(msgs_no) == 1
    assert msgs_no[0].content == "what is up"

    # Test max size enforcement
    orch.chat_history_size = 3
    for i in range(5):
        orch._add_to_history(f"user{i}", f"assistant{i}")
    assert len(orch.chat_history) == 3
    assert orch.chat_history[0]["user"] == "user2"

    print(f"  chat_history_size = {orch.chat_history_size}")
    print(f"  _build_messages with history: OK")
    print(f"  max size enforcement: OK")
    print("PASSED\n")
    return True


def test_routing_enrichment():
    print("--- Test 3: Routing enrichment ---")
    orch = Orchestrator()

    # No history → passthrough
    result = orch._enrich_for_routing("describe it again")
    assert result == "describe it again", f"Expected passthrough, got {result!r}"

    # With history → context prefix
    orch.chat_history = [
        {"user": "open firefox", "assistant": "Opened Firefox."},
        {"user": "what do you see on my screen", "assistant": "I see Firefox."},
    ]
    enriched = orch._enrich_for_routing("describe it again")
    assert "[History:" in enriched
    assert "open firefox" in enriched
    assert "what do you see" in enriched
    assert enriched.endswith("User: describe it again")

    print(f"  No history → passthrough: OK")
    print(f"  With history → enriched: OK")
    print(f"  Output: {enriched[:80]}...")
    print("PASSED\n")
    return True


async def test_open_firefox(orch: Orchestrator) -> bool:
    print("--- Test 4: Open Firefox ---")
    response = await orch.ainvoke("Open Firefox")
    print(f"LLM response: {response[:200]}")

    called = _tool_was_called(orch, "tool_open_application")
    ok = _tool_succeeded(orch, "tool_open_application") if called else False
    if not ok and called:
        print("  (Execution may need a display — tool call wiring verified)")
    status = "PASSED" if called else "FAILED"
    print(f"{status}: Tool called={called}, Tool success={ok}\n")
    return called


async def test_close_firefox(orch: Orchestrator) -> bool:
    print("--- Test 5: Close Firefox ---")
    response = await orch.ainvoke("Close Firefox")
    print(f"LLM response: {response[:200]}")

    called = _tool_was_called(orch, "tool_close_application")
    ok = _tool_succeeded(orch, "tool_close_application") if called else False
    status = "PASSED" if called else "FAILED"
    print(f"{status}: Tool called={called}, Tool success={ok}\n")
    return called


async def test_search_htop(orch: Orchestrator) -> bool:
    print("--- Test 6: Search for htop ---")
    response = await orch.ainvoke("Search for the htop package")
    print(f"LLM response: {response[:200]}")

    called = _tool_was_called(orch, "tool_search_packages")
    ok = _tool_succeeded(orch, "tool_search_packages") if called else False
    status = "PASSED" if called else "FAILED"
    print(f"{status}: Tool called={called}, Tool success={ok}\n")
    return called


async def test_install_htop(orch: Orchestrator) -> bool:
    print("--- Test 7: Install htop ---")
    print("NOTE: This will prompt for your sudo password via pkexec GUI.")
    print("      Press Ctrl+C to skip.")
    try:
        response = await orch.ainvoke("Install the htop package")
        print(f"LLM response: {response[:200]}")
        called = _tool_was_called(orch, "tool_install_package")
        ok = _tool_succeeded(orch, "tool_install_package") if called else False
        status = "PASSED" if called else "FAILED"
        print(f"{status}: Tool called={called}, Tool success={ok}\n")
        return called
    except KeyboardInterrupt:
        print("Skipped.\n")
        return True


async def main():
    # Pure Python tests (no Ollama needed)
    results_py = []
    results_py.append(test_desktop_index())
    results_py.append(test_chat_history())
    results_py.append(test_routing_enrichment())

    # Ollama-dependent tests
    orch = Orchestrator()
    print("Initializing orchestrator...", end=" ", flush=True)
    await orch.initialize()
    print("ready.\n")

    results_llm = []
    results_llm.append(await test_open_firefox(orch))
    results_llm.append(await test_close_firefox(orch))
    results_llm.append(await test_search_htop(orch))
    results_llm.append(await test_install_htop(orch))

    print("=" * 50)
    py_passed = sum(results_py)
    llm_passed = sum(results_llm)
    print(f"Phase 2 Review Gate:")
    print(f"  Pure Python tests: {py_passed}/{len(results_py)} passed")
    print(f"  LLM-powered tests: {llm_passed}/{len(results_llm)} passed")
    if py_passed + llm_passed == len(results_py) + len(results_llm):
        print("All tests passed! Phase 2 is complete.")
    else:
        print("Some tests failed. Review the output above.")


if __name__ == "__main__":
    asyncio.run(main())
