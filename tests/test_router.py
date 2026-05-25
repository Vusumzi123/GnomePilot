"""Tests for src/router.py."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.router import Router


class FakeLLM:
    """Mock ChatOllama that returns a predefined answer."""
    def __init__(self, answer: str):
        self._answer = answer

    async def ainvoke(self, messages):
        return FakeMessage(self._answer)


class FakeMessage:
    def __init__(self, content):
        self.content = content


async def test_regex_screen_only():
    r = Router(llm=FakeLLM("no"))
    agents = await r.route("what is on my screen")
    assert agents == ["vision"]
    print("  screen → vision: OK")


async def test_regex_action_only():
    r = Router(llm=FakeLLM("no"))
    agents = await r.route("open firefox")
    assert agents == ["general"]
    print("  action → general: OK")


async def test_regex_chain():
    r = Router(llm=FakeLLM("no"))
    agents = await r.route("what do you see on my screen and open firefox")
    assert agents == ["vision", "general"]
    print("  screen+action → chain: OK")


async def test_regex_look_at():
    r = Router(llm=FakeLLM("no"))
    agents = await r.route("take a look at my screen")
    assert agents == ["vision"]
    print("  'take a look' → vision: OK")


async def test_regex_move():
    r = Router(llm=FakeLLM("no"))
    agents = await r.route("move terminal to workspace 3")
    assert agents == ["general"]
    print("  'move' → general: OK")


async def test_llm_vision():
    r = Router(llm=FakeLLM("yes"))
    r.prompt = "Is the user asking about their screen?"
    agents = await r.route("what can you see?")
    assert agents == ["vision"]
    print("  LLM 'yes' → vision: OK")


async def test_llm_general():
    r = Router(llm=FakeLLM("no"))
    r.prompt = "Is the user asking about their screen?"
    agents = await r.route("hello system")
    assert agents == ["general"]
    print("  LLM 'no' → general: OK")


async def test_regex_no_false_chain_from_enriched():
    """Regex runs on original input, not enriched.  Even if enriched contains
    'screen', the original 'move firefox' is action-only → general."""
    r = Router(llm=FakeLLM("no"))
    agents = await r.route("move firefox to workspace 2",
                           enriched="[History: what is on my screen] User: move firefox to workspace 2")
    assert agents == ["general"], f"Expected [general], got {agents}"
    print("  no false chain from history words: OK")


async def test_llm_with_enriched_context():
    """LLM receives enriched context and answers 'yes' when history mentions
    the screen, routing a vague 'describe it again' to vision."""
    r = Router(llm=FakeLLM("yes"))
    r.prompt = "Is the user asking about their screen?"
    agents = await r.route("describe it again",
                           enriched="[History: what is on my screen] User: describe it again")
    assert agents == ["vision"]
    print("  enriched context → LLM routes to vision: OK")


async def test_empty_prompt_skips_llm():
    r = Router(llm=FakeLLM("yes"))
    r.prompt = ""
    # Should skip LLM entirely, fall back to ["general"]
    agents = await r.route("hello system")
    assert agents == ["general"]
    print("  empty prompt skip: OK")


async def test_llm_exception_graceful():
    class BrokenLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("Ollama not running")

    r = Router(llm=BrokenLLM())
    r.prompt = "Is the user asking about their screen?"
    agents = await r.route("hello")
    assert agents == ["general"]
    print("  LLM exception → general fallback: OK")


async def main():
    await test_regex_screen_only()
    await test_regex_action_only()
    await test_regex_chain()
    await test_regex_look_at()
    await test_regex_move()
    await test_llm_vision()
    await test_llm_general()
    await test_regex_no_false_chain_from_enriched()
    await test_llm_with_enriched_context()
    await test_empty_prompt_skips_llm()
    await test_llm_exception_graceful()
    print()
    print("=" * 50)
    print("All Router tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
