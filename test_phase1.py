"""Phase 1 Review Gate Tests.

Test 1: Core orchestrator import + async text response
Test 2: TTS audible output verification
Test 3: Fuzzy match scoring (new module)
Test 4: Config loading (debug, chat_history_size)
Test 5: Debug system import + callback handler
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.orchestrator import Orchestrator
from src.voice import speak
from src.tools.fuzzy_match import score, best, ranked
from src.config import load_config, debug_enabled, debug_verbose, chat_history_size


async def test_orchestrator_text_response():
    print("--- Test 1: LLM text response ---")
    orch = Orchestrator()
    await orch.initialize()
    response = await orch.ainvoke("Hello system")
    print(f"User input: 'Hello system'")
    print(f"LLM response: {response[:200]}")
    assert len(response) > 0, "LLM returned empty response"
    print("PASSED\n")


def test_tts_audible_output():
    print("--- Test 2: TTS audible output ---")
    print("Speaking: 'Hello! This is a Phase 1 TTS test. Did you hear me?'")
    speak("Hello! This is a Phase 1 TTS test. Did you hear me?")
    print("PASSED: speak() completed without errors. Verify you heard audio.\n")


def test_fuzzy_match():
    print("--- Test 3: Fuzzy match module ---")
    # Exact
    assert score("firefox", "Firefox") == 100
    assert score("HELLO", "hello") == 100
    # Prefix word
    assert score("firefox", "Firefox Web Browser") == 90
    assert score("obsidian", "Obsidian - My Vault") == 90
    # Whole word within (re.search fix)
    assert score("web", "Firefox Web Browser") == 70
    # Substring
    assert score("irefo", "Firefox") == 50
    assert score("web", "WebStorm") == 50
    # No match
    assert score("xyz", "Firefox") == 0

    candidates = ["Firefox", "Firefox Web Browser", "Chrome", "Obsidian"]
    assert best("firefox", candidates) == "Firefox"
    assert best("web", candidates) == "Firefox Web Browser"
    assert best("chrome", candidates) == "Chrome"
    assert best("safari", candidates) is None

    r = ranked("web", ["Web Browser", "WebStorm", "Ubuntu Web", "Terminal"])
    assert r[0] == ("Web Browser", 90)
    assert r[1] == ("Ubuntu Web", 70)
    assert r[2] == ("WebStorm", 50)

    print(f"  score()  tested: OK")
    print(f"  best()   tested: OK")
    print(f"  ranked() tested: OK")
    print("PASSED\n")


def test_config():
    print("--- Test 4: Config loading ---")
    cfg = load_config()
    assert "models" in cfg
    assert "orchestrator" in cfg
    assert "debug" in cfg

    history_size = chat_history_size()
    assert isinstance(history_size, int) and history_size >= 0

    dbg = debug_enabled()
    assert isinstance(dbg, bool)

    vrb = debug_verbose()
    assert isinstance(vrb, bool)

    print(f"  chat_history_size = {history_size}")
    print(f"  debug.enabled     = {dbg}")
    print(f"  debug.verbose     = {vrb}")
    print("PASSED\n")


def test_debug_module():
    print("--- Test 5: Debug module ---")
    from src.debug import DebugCallbackHandler
    handler = DebugCallbackHandler(verbose=False)
    assert handler.verbose is False

    handler2 = DebugCallbackHandler(verbose=True)
    assert handler2.verbose is True

    # Verify configure() works without crashing
    from src.debug import configure
    from loguru import logger
    configure(verbose=False, log_dir="/tmp/test_phase1_debug", retention_days=1, rotation="1 MB")
    logger.info("Debug system: functional")
    logger.debug("This DEBUG message should NOT appear when verbose=False")

    print("  DebugCallbackHandler instantiated: OK")
    print("  Loguru sinks configured: OK")
    print("PASSED\n")


async def main():
    await test_orchestrator_text_response()
    test_tts_audible_output()
    test_fuzzy_match()
    test_config()
    test_debug_module()

    print("=" * 50)
    print("Phase 1 Review Gate tests complete.")
    print("Verify: Did you hear the spoken audio?")


if __name__ == "__main__":
    asyncio.run(main())
