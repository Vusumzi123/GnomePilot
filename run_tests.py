#!/usr/bin/env python3
"""Dynamic test runner — discovers and executes all test_*.py files, prints
per-test output inline, and shows a final summary with individual test stats.

Usage:
    python3 run_tests.py              # run all tests
    python3 run_tests.py --unit       # run only unit tests (no Ollama needed)
    python3 run_tests.py --integration # run only integration tests (need Ollama)
    python3 run_tests.py --timeout N  # set timeout per test in seconds (default 120)
    python3 run_tests.py test_router  # run only matching test files
"""

import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# Tests that need a running Ollama server
_INTEGRATION_TESTS = {"test_agents", "test_executor", "test_pipeline", "test_close"}

_LOGURU_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "SUCCESS")


def discover_tests() -> list[Path]:
    """Return all test_*.py files, unit tests first."""
    tests: list[Path] = []
    for f in sorted(PROJECT_DIR.glob("test_*.py")):
        if f.name != Path(__file__).name:
            tests.append(f)
    tests.sort(key=lambda p: (p.stem in _INTEGRATION_TESTS, p.stem))
    return tests


def _count_passes(stdout: str) -> int:
    """Count individual test assertions that passed in this file's output."""
    return sum(1 for _ in re.finditer(r":\s*OK[!\s]", stdout))


def _count_total(stdout: str) -> int:
    """Count individual test assertions that ran (pass + fail markers)."""
    return sum(1 for _ in re.finditer(r":\s*OK(?:[!\s]|$)", stdout))


def run_one(test_path: Path, timeout: int) -> tuple[str, bool, float, str]:
    """Execute a single test file. Returns (stem, passed, duration, full_stdout)."""
    start = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(test_path)],
            capture_output=True, text=True,
            timeout=timeout,
            cwd=str(PROJECT_DIR),
            env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"},
        )
        duration = time.monotonic() - start
        passed = result.returncode == 0
        full_output = result.stdout.strip()
        return test_path.stem, passed, duration, full_output
    except subprocess.TimeoutExpired as e:
        duration = time.monotonic() - start
        err = e.stderr.decode() if e.stderr else ""
        return test_path.stem, False, duration, f"TIMEOUT ({timeout}s)\n{err}"
    except Exception as e:
        duration = time.monotonic() - start
        return test_path.stem, False, duration, str(e)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Dynamic test runner — verbose")
    parser.add_argument("filter", nargs="*", help="Test name filter(s), e.g. test_router")
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--timeout", type=int, default=120, help="Seconds per test (default 120)")
    parser.add_argument("--quiet", action="store_true", help="Show only summary, not per-test output")
    args = parser.parse_args()

    tests = discover_tests()

    if args.filter:
        tests = [t for t in tests if any(f in t.stem for f in args.filter)]
    if args.unit:
        tests = [t for t in tests if t.stem not in _INTEGRATION_TESTS]
    if args.integration:
        tests = [t for t in tests if t.stem in _INTEGRATION_TESTS]

    if not tests:
        print("No matching test files found.")
        print(f"Available tests: {', '.join(t.stem for t in discover_tests())}")
        return

    print("=" * 60)
    print(f" Test runner — {len(tests)} suite(s)")
    if args.unit:
        print("   Mode: unit only")
    elif args.integration:
        print("   Mode: integration only")
    print(f"   Timeout: {args.timeout}s per suite")
    print("=" * 60)
    print()

    results: list[tuple[str, bool, float, str, int, int]] = []

    for i, test_path in enumerate(tests):
        is_integration = test_path.stem in _INTEGRATION_TESTS
        tag = "INTEGRATION" if is_integration else "UNIT"
        print(f"┌─ [{i+1}/{len(tests)}] {tag} {test_path.stem} "
              f"{'─' * (48 - len(test_path.stem) - len(tag) - 6)}")

        stem, passed, duration, output = run_one(test_path, timeout=args.timeout)

        p = _count_passes(output)
        t = max(p, 1)  # at minimum count the suite-level pass
        results.append((stem, passed, duration, output, p, t))

        if not args.quiet:
            for line in output.split("\n"):
                # Strip ANSI sequences + Loguru timestamps
                clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
                clean = re.sub(r"^\d{4}-\d{2}-\d{2} [\d:.]+ \| ", "", clean)
                # Skip remaining Loguru-level lines
                if re.match(rf"^\s*({'|'.join(_LOGURU_LEVELS)})\s", clean):
                    continue
                if clean.strip():
                    print(f"│ {clean.strip()}")
            print("│")

        status = "\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m"
        print(f"└─ {status} ({duration:.1f}s)")
        print()

    # ── Summary ──
    print("=" * 60)
    print(" Summary")
    print("=" * 60)

    max_name = max(len(r[0]) for r in results) if results else 10
    total_passed_suites = 0
    total_assertions = 0
    total_duration = 0.0

    for stem, passed, duration, _, p, t in results:
        status = "\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m"
        print(f"  {stem:{max_name}}  {status}  ~{p} checks  ({duration:.1f}s)")
        if passed:
            total_passed_suites += 1
        total_assertions += p
        total_duration += duration

    print()
    print(f"  Suites:  {total_passed_suites}/{len(results)} passed")
    print(f"  Checks:  ~{total_assertions} assertions")
    print(f"  Time:    {total_duration:.1f}s")
    print()

    if total_passed_suites == len(results):
        print(f"\033[32m All suites passed\033[0m")
    else:
        print(f"\033[31m {total_passed_suites}/{len(results)} passed, "
              f"{len(results) - total_passed_suites} failed\033[0m")

        failed = [(s, d, o) for s, p, d, o, _, _ in results if not p]
        if failed:
            print()
            print("Failing suites:")
            for stem, duration, output in failed:
                print(f"  ✗ {stem} ({duration:.1f}s)")
                for line in output.split("\n")[-10:]:
                    print(f"    {line}")

    return 0 if total_passed_suites == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
