"""Tests for src/executor.py — unit tests mock agents, integration tests need Ollama."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.executor import Executor, AgentResult
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ── helpers for unit tests (no Ollama needed) ──

class _FakeAgent:
    """Returns controlled messages, simulating agent.ainvoke."""
    def __init__(self, messages):
        self._messages = messages
        self.last_input = None

    async def ainvoke(self, input, config=None):
        self.last_input = input
        return {"messages": self._messages}


class _FakeAgents:
    def __init__(self, general_messages=None, vision_messages=None):
        self.general = _FakeAgent(general_messages or [])
        self.vision = _FakeAgent(vision_messages or [])


# ── pure sync unit tests ──

def test_agent_result():
    r = AgentResult(text="Hello", tool_calls=[{"name": "t", "args": {}, "result": "ok"}],
                    vision_context="I see Firefox.")
    assert r.text == "Hello"
    assert len(r.tool_calls) == 1
    assert r.vision_context == "I see Firefox."
    print("  AgentResult dataclass: OK")


def test_agent_result_defaults():
    r = AgentResult(text="ok")
    assert r.tool_calls == []
    assert r.vision_context == ""
    print("  AgentResult defaults: OK")


# ── async unit tests (mock agents, no Ollama) ──

async def test_empty_agents_order_returns_blank():
    agents = _FakeAgents()
    executor = Executor(agents=agents)
    result = await executor.execute([], [HumanMessage(content="test")])
    assert result.text == ""
    assert result.tool_calls == []
    print("  empty order → blank result: OK")


async def test_dedup_detection_prepends_warning():
    ai_msg = AIMessage(content="done", tool_calls=[
        {"name": "tool_x", "args": {"a": 1}, "id": "1"},
        {"name": "tool_x", "args": {"a": 1}, "id": "2"},
    ])
    tool_msg1 = ToolMessage(content="ok", name="tool_x", tool_call_id="1")
    tool_msg2 = ToolMessage(content="ok", name="tool_x", tool_call_id="2")
    agents = _FakeAgents(general_messages=[ai_msg, tool_msg1, tool_msg2])
    executor = Executor(agents=agents)
    result = await executor.execute(["general"], [HumanMessage(content="test")])
    assert "I was unable to complete your request" in result.text
    assert len(result.tool_calls) == 2
    print("  dedup warning prepended: OK")


async def test_no_false_dedup_for_different_args():
    ai_msg = AIMessage(content="done", tool_calls=[
        {"name": "tool_x", "args": {"a": 1}, "id": "1"},
        {"name": "tool_x", "args": {"a": 2}, "id": "2"},
    ])
    tool_msg1 = ToolMessage(content="ok", name="tool_x", tool_call_id="1")
    tool_msg2 = ToolMessage(content="ok", name="tool_x", tool_call_id="2")
    agents = _FakeAgents(general_messages=[ai_msg, tool_msg1, tool_msg2])
    executor = Executor(agents=agents)
    result = await executor.execute(["general"], [HumanMessage(content="test")])
    assert "I was unable to complete your request" not in result.text
    print("  different args → no false dedup: OK")


async def test_no_false_dedup_for_different_names():
    ai_msg = AIMessage(content="done", tool_calls=[
        {"name": "tool_a", "args": {"x": 1}, "id": "1"},
        {"name": "tool_b", "args": {"x": 1}, "id": "2"},
    ])
    tool_msg1 = ToolMessage(content="ok", name="tool_a", tool_call_id="1")
    tool_msg2 = ToolMessage(content="ok", name="tool_b", tool_call_id="2")
    agents = _FakeAgents(general_messages=[ai_msg, tool_msg1, tool_msg2])
    executor = Executor(agents=agents)
    result = await executor.execute(["general"], [HumanMessage(content="test")])
    assert "I was unable to complete your request" not in result.text
    print("  different names → no false dedup: OK")


async def test_vision_context_prepopulated_crafts_prompt():
    ai_msg = AIMessage(content="Opening Firefox", tool_calls=[])
    agents = _FakeAgents(general_messages=[ai_msg])
    executor = Executor(agents=agents)
    result = await executor.execute(
        ["general"], [HumanMessage(content="irrelevant")],
        vision_context="I see Firefox on screen.",
        user_input="open firefox",
    )
    input_content = agents.general.last_input["messages"][0].content
    assert "Context from vision analysis" in input_content
    assert "I see Firefox on screen." in input_content
    assert "open firefox" in input_content
    assert result.text == "Opening Firefox"
    print("  vision context prepopulated → crafts prompt: OK")


async def test_chain_vision_to_general():
    vision_ai = AIMessage(content="I see Firefox on screen.", tool_calls=[])
    general_ai = AIMessage(content="Opening Firefox.", tool_calls=[])
    agents = _FakeAgents(
        general_messages=[general_ai],
        vision_messages=[vision_ai],
    )
    executor = Executor(agents=agents)
    result = await executor.execute(
        ["vision", "general"], [HumanMessage(content="open firefox")],
        user_input="open firefox",
    )
    input_content = agents.general.last_input["messages"][0].content
    assert "Context from vision analysis" in input_content
    assert "I see Firefox on screen." in input_content
    assert result.text == "Opening Firefox."
    assert result.vision_context == "I see Firefox on screen."
    print("  chain vision→general: OK")


async def test_single_vision_agent_sets_vision_context():
    vision_ai = AIMessage(content="I see a terminal window.", tool_calls=[])
    agents = _FakeAgents(vision_messages=[vision_ai])
    executor = Executor(agents=agents)
    result = await executor.execute(["vision"], [HumanMessage(content="look")])
    assert result.vision_context == "I see a terminal window."
    assert result.text == "I see a terminal window."
    print("  single vision → sets vision_context: OK")


async def test_tool_calls_aggregate_across_chain():
    vision_ai = AIMessage(content="I see Firefox.", tool_calls=[
        {"name": "tool_capture_screen", "args": {}, "id": "1"},
    ])
    general_ai = AIMessage(content="Opening Firefox.", tool_calls=[
        {"name": "tool_open_application", "args": {"app_name": "firefox"}, "id": "2"},
    ])
    tool_msg1 = ToolMessage(content="captured", name="tool_capture_screen",
                            tool_call_id="1")
    tool_msg2 = ToolMessage(content="opened", name="tool_open_application",
                            tool_call_id="2")
    agents = _FakeAgents(
        general_messages=[general_ai, tool_msg2],
        vision_messages=[vision_ai, tool_msg1],
    )
    executor = Executor(agents=agents)
    result = await executor.execute(
        ["vision", "general"], [HumanMessage(content="open firefox")],
        user_input="open firefox",
    )
    assert len(result.tool_calls) == 2
    names = [c["name"] for c in result.tool_calls]
    assert "tool_capture_screen" in names
    assert "tool_open_application" in names
    print("  tool calls aggregate across chain: OK")


# ── integration tests (need Ollama) ──

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
    print(f"  tool calls tracked: {len(result.tool_calls)} calls "
          f"({[c['name'] for c in result.tool_calls]})")
    print("  tool_call tracking: OK")

    await a.shutdown()


async def main():
    test_agent_result()
    test_agent_result_defaults()
    await test_empty_agents_order_returns_blank()
    await test_dedup_detection_prepends_warning()
    await test_no_false_dedup_for_different_args()
    await test_no_false_dedup_for_different_names()
    await test_vision_context_prepopulated_crafts_prompt()
    await test_chain_vision_to_general()
    await test_single_vision_agent_sets_vision_context()
    await test_tool_calls_aggregate_across_chain()

    await test_single_agent()
    await test_executor_tracks_tool_calls()

    print()
    print("=" * 50)
    print("All Executor tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
