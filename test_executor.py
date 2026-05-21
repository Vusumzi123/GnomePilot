"""Tests for src/executor.py — requires Ollama running for integration tests."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.executor import Executor, AgentResult
from langchain_core.messages import HumanMessage


def test_agent_result():
    r = AgentResult(text="Hello", tool_calls=[{"name": "t", "args": {}, "result": "ok"}],
                    vision_context="I see Firefox.")
    assert r.text == "Hello"
    assert len(r.tool_calls) == 1
    assert r.vision_context == "I see Firefox."
    print("  AgentResult dataclass: OK")


async def test_single_agent():
    """Execute a single general agent."""
    from src.agents import Agents
    a = Agents()
    await a.start()

    ex = Executor(agents=a)
    messages = [HumanMessage(content="Hello system")]
    result = await ex.execute(["general"], messages)

    assert isinstance(result, AgentResult)
    assert len(result.text) > 0
    print(f"  single agent: returned {len(result.text)} chars: {result.text[:80]}...")
    print("  single agent: OK")

    await a.shutdown()


async def test_executor_tracks_tool_calls():
    from src.agents import Agents
    a = Agents()
    await a.start()

    ex = Executor(agents=a)
    messages = [HumanMessage(content="Open Firefox")]
    result = await ex.execute(["general"], messages)

    assert len(result.text) > 0
    assert isinstance(result.tool_calls, list)
    print(f"  tool calls tracked: {len(result.tool_calls)} calls ({[c['name'] for c in result.tool_calls]})")
    print("  tool_call tracking: OK")

    await a.shutdown()


async def main():
    test_agent_result()

    await test_single_agent()
    await test_executor_tracks_tool_calls()

    print()
    print("=" * 50)
    print("All Executor tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
