"""Phase 1 Review Gate Tests.

Test 1: LLM text response to "Hello system"
Test 2: TTS audible output verification
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.orchestrator import Orchestrator
from src.voice import speak


def test_orchestrator_text_response():
    print("--- Test 1: LLM text response ---")
    orchestrator = Orchestrator()
    response = orchestrator.invoke("Hello system")
    print(f"User input: 'Hello system'")
    print(f"LLM response: {response}")
    assert len(response) > 0, "LLM returned empty response"
    print("PASSED: LLM responded with non-empty text.\n")


def test_tts_audible_output():
    print("--- Test 2: TTS audible output ---")
    print("Speaking: 'Hello! This is a Phase 1 TTS test. Did you hear me?'")
    speak("Hello! This is a Phase 1 TTS test. Did you hear me?")
    print("PASSED: TTS speak() completed without errors. Verify you heard audio.\n")


if __name__ == "__main__":
    test_orchestrator_text_response()
    test_tts_audible_output()
    print("=" * 40)
    print("Phase 1 Review Gate tests complete.")
    print("Verify: Did you hear the spoken audio?")
