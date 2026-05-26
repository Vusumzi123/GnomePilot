"""Tests for src/tools/fuzzy_match.py — generic string scorer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.fuzzy_match import score, best, ranked


def test_score_exact_match():
    assert score("firefox", "Firefox") == 100
    assert score("FIREFOX", "firefox") == 100
    print("  score exact match: OK")


def test_score_prefix_match():
    assert score("obsidian", "Obsidian - My Vault") == 90
    print("  score prefix match: OK")


def test_score_whole_word_match():
    assert score("music", "YouTube Music - Browser") == 70
    assert score("browser", "Firefox Web Browser") == 70
    print("  score whole-word match: OK")


def test_score_substring_match():
    assert score("sidian", "Obsidian - Vault") == 50
    print("  score substring match: OK")


def test_score_no_match():
    assert score("zzz", "Firefox") == 0
    print("  score no match: OK")


def test_score_empty_strings():
    assert score("", "Firefox") == 0
    assert score("firefox", "") == 0
    assert score("", "") == 0
    print("  score empty strings: OK")


def test_score_regex_safety():
    assert score("file.txt", "file.txt is open") == 90
    assert score("http://test.com", "http://test.com page") == 90
    print("  score regex safety: OK")


def test_score_whitespace_handling():
    assert score("  firefox  ", "Firefox") == 100
    assert score("firefox", "  Firefox  ") == 100
    print("  score whitespace handling: OK")


def test_best_returns_best_match():
    titles = ["Obsidian - Vault", "Firefox", "Firefox Web Browser"]
    assert best("firefox", titles) == "Firefox"
    print("  best returns Firefox: OK")


def test_best_returns_none_below_threshold():
    titles = ["Firefox", "Chrome"]
    assert best("notepad", titles) is None
    print("  best below threshold → None: OK")


def test_best_respects_custom_threshold():
    titles = ["Obsidian - Vault", "Firefox"]
    assert best("sidian", titles, threshold=60) is None
    assert best("sidian", titles, threshold=50) == "Obsidian - Vault"
    print("  best custom threshold: OK")


def test_best_empty_candidates():
    assert best("firefox", []) is None
    print("  best empty candidates → None: OK")


def test_ranked_returns_sorted_results():
    titles = ["YouTube Music", "YouTube", "Firefox"]
    results = ranked("youtube", titles, threshold=1)
    assert len(results) == 2
    assert results[0][0] == "YouTube"
    assert results[0][1] == 100
    assert results[1][0] == "YouTube Music"
    assert results[0][1] >= results[1][1]
    print("  ranked sorted: OK")


def test_ranked_respects_threshold():
    titles = ["Obsidian - Vault", "Firefox", "YouTube"]
    results = ranked("sidian", titles, threshold=60)
    assert len(results) == 0
    results = ranked("sidian", titles, threshold=50)
    assert len(results) == 1
    assert results[0][0] == "Obsidian - Vault"
    print("  ranked threshold: OK")


def test_ranked_empty_candidates():
    assert ranked("x", []) == []
    print("  ranked empty candidates: OK")


if __name__ == "__main__":
    test_score_exact_match()
    test_score_prefix_match()
    test_score_whole_word_match()
    test_score_substring_match()
    test_score_no_match()
    test_score_empty_strings()
    test_score_regex_safety()
    test_score_whitespace_handling()
    test_best_returns_best_match()
    test_best_returns_none_below_threshold()
    test_best_respects_custom_threshold()
    test_best_empty_candidates()
    test_ranked_returns_sorted_results()
    test_ranked_respects_threshold()
    test_ranked_empty_candidates()
    print()
    print("=" * 50)
    print("All fuzzy_match tests passed.")
