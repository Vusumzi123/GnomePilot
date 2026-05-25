"""Tests for deferred tool registry (Step 1 of PLAN_SKILL_AUTO_DISCOVERY.md)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools._registry import tool, collect


def test_collect_single():
    @tool()
    def fn_a(x: int) -> str:
        """Does A."""
        return str(x)

    result = collect()
    assert len(result) == 1
    assert result[0][0] is fn_a
    assert result[0][1] == {}
    print("  single collect: OK")


def test_collect_multiple():
    @tool(name="custom_name")
    def fn_b(x: str) -> str:
        """Does B."""
        return x

    @tool()
    def fn_c(y: float) -> float:
        """Does C."""
        return y * 2

    result = collect()
    assert len(result) == 2
    assert result[0][1] == {"name": "custom_name"}
    assert result[1][1] == {}
    print("  multiple collect with kwargs: OK")


def test_collect_drains():
    @tool()
    def fn_d() -> None:
        pass

    result1 = collect()
    assert len(result1) == 1
    result2 = collect()
    assert result2 == []
    print("  collect drains after call: OK")


def test_empty_collect_returns_list():
    result = collect()
    assert isinstance(result, list)
    assert result == []
    print("  empty collect: OK")


if __name__ == "__main__":
    test_collect_single()
    test_collect_multiple()
    test_collect_drains()
    test_empty_collect_returns_list()
    print()
    print("=" * 50)
    print("All registry tests passed.")
