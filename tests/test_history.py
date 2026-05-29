"""Tests for src/history.py — zero-dependency."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.history import History
from langchain_core.messages import HumanMessage, AIMessage


def test_add_and_count():
    h = History(max_turns=10)
    assert h.turns == 0

    h.add_turn("hello", "Hi there!")
    assert h.turns == 1
    assert h._turns[0]["user"] == "hello"
    assert h._turns[0]["assistant"] == "Hi there!"

    h.add_turn("open firefox", "Opened Firefox.")
    assert h.turns == 2
    print("  add_turn + turns: OK")


def test_max_size_enforcement():
    h = History(max_turns=3)
    for i in range(5):
        h.add_turn(f"user{i}", f"assistant{i}")
    assert h.turns == 3
    assert h._turns[0]["user"] == "user2"
    assert h._turns[-1]["user"] == "user4"
    print("  max_turns enforcement: OK")


def test_disabled_history():
    h = History(max_turns=0)
    h.add_turn("hello", "Hi")
    assert h.turns == 0
    print("  max_turns=0 disables: OK")


def test_build_messages_with_history():
    h = History(max_turns=10)
    h.add_turn("hello", "Hi there!")
    h.add_turn("open firefox", "Opened Firefox.")

    msgs = h.build_messages("what is up", include_history=True)
    assert len(msgs) == 5  # 2 pairs (4) + 1 current = 5 (no preamble)
    assert isinstance(msgs[0], HumanMessage)
    assert msgs[0].content == "hello"
    assert isinstance(msgs[1], AIMessage)
    assert msgs[1].content == "Hi there!"
    assert isinstance(msgs[2], HumanMessage)
    assert msgs[2].content == "open firefox"
    assert isinstance(msgs[3], AIMessage)
    assert msgs[3].content == "Opened Firefox."
    assert isinstance(msgs[4], HumanMessage)
    assert msgs[4].content == "what is up"
    print("  build_messages with history: OK")


def test_build_messages_without_history():
    h = History(max_turns=10)
    h.add_turn("hello", "Hi")
    msgs = h.build_messages("close it", include_history=False)
    assert len(msgs) == 1
    assert isinstance(msgs[0], HumanMessage)
    assert msgs[0].content == "close it"
    print("  build_messages without history: OK")


def test_empty_history_build():
    h = History(max_turns=10)
    msgs = h.build_messages("hello", include_history=True)
    assert len(msgs) == 1
    assert msgs[0].content == "hello"
    print("  empty history build: OK")


def test_enrich_passthrough():
    h = History(max_turns=10)
    result = h.enrich_for_routing("describe it again")
    assert result == "describe it again"
    print("  enrich (no history) → passthrough: OK")

    h2 = History(max_turns=0)
    h2.add_turn("hello", "Hi")
    result = h2.enrich_for_routing("describe it again")
    assert result == "describe it again"
    print("  enrich (disabled) → passthrough: OK")


def test_enrich_with_context():
    h = History(max_turns=10)
    h.add_turn("open firefox", "Opened Firefox.")
    h.add_turn("what do you see on my screen", "I see Firefox.")
    h.add_turn("what is that", "A GitHub repo page.")

    enriched = h.enrich_for_routing("describe it again")
    assert "[History:" in enriched
    assert "open firefox" in enriched
    assert "what do you see on my screen" in enriched
    assert "what is that" in enriched
    assert enriched.endswith("User: describe it again")
    print("  enrich with history: OK")


def test_enrich_truncation():
    h = History(max_turns=10)
    long = "a" * 200
    h.add_turn(long, "ok")
    enriched = h.enrich_for_routing("test")
    assert len(enriched) < len(long) + 200  # not just concatenated raw
    print("  enrich truncation: OK")


def test_clear():
    h = History(max_turns=10)
    h.add_turn("hello", "Hi")
    assert h.turns == 1
    h.clear()
    assert h.turns == 0
    print("  clear: OK")


# ── token trimming tests ──


def test_token_budget_trimmed():
    """When token budget is exceeded, oldest turns are dropped."""
    h = History(max_turns=10, max_tokens=100)
    big = "X" * 400  # 400 chars → ~100 tokens
    h.add_turn("hello", big)       # ~1 + ~100 = ~101 tokens (already over budget alone)
    h.add_turn("how are you", big)  # ~2 + ~100 = ~102 — total ~203 > 100 budget
    # First turn should be trimmed, second kept
    assert h.turns == 1, f"Expected 1 turn, got {h.turns}"
    assert h._turns[0]["user"] == "how are you"
    print("  token budget trimmed oldest: OK")


def test_token_budget_keeps_one():
    """A single turn that exceeds the budget is still kept."""
    h = History(max_turns=10, max_tokens=50)
    long_response = "X" * 400  # ~100 tokens — exceeds 50 budget
    h.add_turn("hello", long_response)
    assert h.turns == 1, "Single turn should be kept even if over budget"
    print("  single turn over budget still kept: OK")


def test_token_budget_disabled():
    """max_tokens <= 0 clears all history."""
    h = History(max_turns=10, max_tokens=0)
    h.add_turn("hello", "Hi")
    assert h.turns == 0, "max_tokens=0 should disable history"
    print("  max_tokens=0 disables: OK")


def test_token_budget_stricter_wins():
    """When both limits are set, the stricter one wins."""
    # max_tokens is very tight, max_turns is generous
    h = History(max_turns=100, max_tokens=50)
    for i in range(5):
        h.add_turn(f"user{i}", "response" * 5)  # ~45 chars → ~11 tokens
    # 5 turns × ~11 tokens = ~55 tokens > 50 budget → should trim
    assert h.turns < 5, f"Token budget should trim, got {h.turns} turns"
    print(f"  stricter budget wins: {h.turns} turns (max_tokens=50, max_turns=100): OK")


def test_estimate_tokens():
    """_estimate_tokens uses chars // 4 approximation."""
    assert History._estimate_tokens("") == 1
    assert History._estimate_tokens("abcd") == 1
    assert History._estimate_tokens("12345678") == 2
    assert History._estimate_tokens("x" * 100) == 25
    print("  _estimate_tokens: OK")


if __name__ == "__main__":
    test_add_and_count()
    test_max_size_enforcement()
    test_disabled_history()
    test_build_messages_with_history()
    test_build_messages_without_history()
    test_empty_history_build()
    test_enrich_passthrough()
    test_enrich_with_context()
    test_enrich_truncation()
    test_clear()
    test_token_budget_trimmed()
    test_token_budget_keeps_one()
    test_token_budget_disabled()
    test_token_budget_stricter_wins()
    test_estimate_tokens()
    print()
    print("=" * 50)
    print("All History tests passed.")
