"""Tests for src/pipeline.py."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.history import History
from src.formatter import Formatter
from src.extractor import Extractor
from src.executor import Executor, AgentResult
from src.pipeline import Pipeline, Context


# ── mocks ──

class FakeRouter:
    def __init__(self, agents: list[str]):
        self._agents = agents

    async def route(self, user_input: str) -> list[str]:
        return list(self._agents)


class FakeExecutor:
    def __init__(self, text: str = "response", tool_calls=None):
        self._text = text
        self._tool_calls = tool_calls or []

    async def execute(self, agents_order, messages, *, vision_context="",
                      user_input="", recursion_limit=10, timeout=60):
        return AgentResult(text=self._text, tool_calls=list(self._tool_calls))


# ── unit tests (no Ollama) ──

async def test_pipeline_unit():
    """Pipeline with mocked Router + Executor should produce formatted output."""
    pipeline = Pipeline(
        router=FakeRouter(["general"]),
        executor=FakeExecutor(text="Hello! How can I help?"),
        history=History(max_turns=10),
        formatter=Formatter(enabled=True),
        extractor=Extractor(),
    )
    result = await pipeline.process("hello")
    assert result == "Hello! How can I help?"
    assert pipeline.context is not None
    assert pipeline.context.agents == ["general"]
    assert pipeline.context.raw_input == "hello"
    assert pipeline.context.error is None
    print("  unit: simple pass-through: OK")


async def test_pipeline_context():
    """Context is populated after each call."""
    pipeline = Pipeline(
        router=FakeRouter(["vision", "general"]),
        executor=FakeExecutor(text="I see Firefox."),
        history=History(max_turns=10),
        formatter=Formatter(enabled=True),
        extractor=Extractor(),
    )
    result = await pipeline.process("what do you see on my screen and open firefox")
    ctx = pipeline.context
    assert ctx.agents == ["vision", "general"]
    assert ctx.formatted == "I see Firefox."
    print("  unit: chain context populated: OK")


async def test_pipeline_tool_calls():
    """Tool calls are tracked."""
    pipeline = Pipeline(
        router=FakeRouter(["general"]),
        executor=FakeExecutor(text="Opened Firefox.",
                              tool_calls=[{"name": "tool_open_application",
                                           "args": {"app_name": "firefox"},
                                           "result": "Opened Firefox."}]),
        history=History(max_turns=10),
        formatter=Formatter(enabled=True),
        extractor=Extractor(),
    )
    await pipeline.process("open firefox")
    assert len(pipeline.last_tool_calls) == 1
    assert pipeline.last_tool_calls[0]["name"] == "tool_open_application"
    print("  unit: tool calls tracked: OK")


async def test_pipeline_history_accumulates():
    """History grows across multiple process() calls."""
    pipeline = Pipeline(
        router=FakeRouter(["general"]),
        executor=FakeExecutor(text="Opened Firefox."),
        history=History(max_turns=10),
        formatter=Formatter(enabled=True),
        extractor=Extractor(),
    )
    await pipeline.process("open firefox")
    assert pipeline.history.turns == 1
    await pipeline.process("close it")
    assert pipeline.history.turns == 2
    await pipeline.process("what was that?")
    assert pipeline.history.turns == 3

    # Third call should have history prepended
    msgs = pipeline.history.build_messages("what was that?", include_history=True)
    assert len(msgs) == 7  # 3 pairs (6) + 1 current = 7 (no preamble)
    assert msgs[0].content == "open firefox"
    print("  unit: history accumulates: OK")


async def test_pipeline_error_handling():
    """Broken Executor → error captured in context, not thrown."""
    class BrokenExecutor:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("Simulated failure")

    pipeline = Pipeline(
        router=FakeRouter(["general"]),
        executor=BrokenExecutor(),
        history=History(max_turns=10),
        formatter=Formatter(enabled=True),
        extractor=Extractor(),
    )
    result = await pipeline.process("hello")
    assert "Simulated failure" in result
    assert pipeline.context.error == "Simulated failure"
    print("  unit: error handling: OK")


async def test_pipeline_formatter():
    """Formatter cleans the response."""
    pipeline = Pipeline(
        router=FakeRouter(["general"]),
        executor=FakeExecutor(text="Hello \U0001F600 world!"),
        history=History(max_turns=10),
        formatter=Formatter(enabled=True),
        extractor=Extractor(),
    )
    result = await pipeline.process("hello")
    assert "\U0001F600" not in result
    print("  unit: formatter integration: OK")


# ── integration tests (needs Ollama) ──

async def test_pipeline_integration():
    """Full pipeline with real Agents."""
    from src.agents import Agents
    from src.router import Router

    agents = Agents()
    await agents.start()

    pipeline = Pipeline(
        router=Router(llm=agents.general_llm, prompt=agents.router_prompt),
        executor=Executor(agents=agents),
        history=History(max_turns=10),
        formatter=Formatter(enabled=True),
        extractor=Extractor(),
    )

    result = await pipeline.process("Hello system")
    assert len(result) > 0
    print(f"  integration: pipeline returned {len(result)} chars: {result[:80]}...")
    print("  integration: OK")

    await agents.shutdown()


async def test_pipeline_integration_chain():
    """Chain routing with real agents."""
    from src.agents import Agents
    from src.router import Router

    agents = Agents()
    await agents.start()

    pipeline = Pipeline(
        router=Router(llm=agents.general_llm, prompt=agents.router_prompt),
        executor=Executor(agents=agents),
        history=History(max_turns=10),
        formatter=Formatter(enabled=True),
        extractor=Extractor(),
    )

    result = await pipeline.process("what do you see on my screen and open firefox")
    assert len(result) > 0
    ctx = pipeline.context
    print(f"  integration chain: agents={ctx.agents}, {len(ctx.tool_calls)} tool calls")
    print("  integration chain: OK")

    await agents.shutdown()


async def main():
    # Unit tests
    await test_pipeline_unit()
    await test_pipeline_context()
    await test_pipeline_tool_calls()
    await test_pipeline_history_accumulates()
    await test_pipeline_error_handling()
    await test_pipeline_formatter()

    # Integration tests
    await test_pipeline_integration()
    await test_pipeline_integration_chain()

    print()
    print("=" * 50)
    print("All Pipeline tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
