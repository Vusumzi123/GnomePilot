"""Tests for src/agents.py — requires Ollama running."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_construction():
    """Agents can be constructed without Ollama."""
    from src.agents import Agents
    a = Agents()
    assert a.general_llm is not None
    assert a.general is None  # not started yet
    assert a.vision is None
    assert len(a.general_prompt) > 0
    assert len(a.vision_prompt) > 0
    print("  construction: OK")


async def test_start_and_agents():
    """After start(), both agents are non-None."""
    from src.agents import Agents
    a = Agents()
    await a.start()

    gen = a.general
    vis = a.vision
    assert gen is not None, "General agent not created"
    assert vis is not None, "Vision agent not created"

    print(f"  start(): general_agent={type(gen).__name__}, vision_agent={type(vis).__name__}")
    print("  agents created: OK")

    await a.shutdown()


async def test_shutdown():
    """Shutdown unloads models without error."""
    from src.agents import Agents
    a = Agents()
    await a.start()
    await a.shutdown()
    print("  shutdown() no errors: OK")


async def main():
    await test_construction()
    await test_start_and_agents()
    await test_shutdown()

    print()
    print("=" * 50)
    print("All Agents tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
