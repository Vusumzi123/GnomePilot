"""Generic fuzzy string matching — reusable for any name-to-list lookup."""

import re


def score(search: str, target: str) -> int:
    """Return match quality: 100=exact, 90=prefix, 70=whole-word, 50=substring, 0=none.

    Both inputs are compared case-insensitively.
    """
    s = search.lower().strip()
    t = target.lower().strip()
    if not s or not t:
        return 0
    if s == t:
        return 100
    if re.search(rf"\b{re.escape(s)}\b", t):
        start = t.index(s)
        if start == 0 and (len(t) == len(s) or not t[len(s)].isalnum()):
            return 90
        return 70
    if s in t:
        return 50
    return 0


def best(search: str, candidates: list[str], threshold: int = 50) -> str | None:
    """Return the highest-scoring candidate, or None if all fall below threshold.

    Ties go to the first candidate encountered (typically pre-sorted by priority).
    """
    best_score = 0
    best_candidate: str | None = None
    for c in candidates:
        s = score(search, c)
        if s > best_score:
            best_score = s
            best_candidate = c
    return best_candidate if best_score >= threshold else None


def ranked(search: str, candidates: list[str], threshold: int = 0) -> list[tuple[str, int]]:
    """Return all matching candidates with their scores, sorted high to low."""
    results = [(c, score(search, c)) for c in candidates]
    results = [(c, s) for c, s in results if s >= threshold]
    results.sort(key=lambda x: x[1], reverse=True)
    return results
