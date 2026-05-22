"""Pipeline — wires Router, Executor, History, Formatter, Extractor into a
single processing chain with a typed Context flowing between stages.
"""

from dataclasses import dataclass, field

from loguru import logger

from src.history import History
from src.formatter import Formatter
from src.extractor import Extractor
from src.router import Router
from src.executor import Executor
from src.config import recursion_limit as cfg_recursion_limit

try:
    from langgraph.errors import GraphRecursionError
except ImportError:
    GraphRecursionError = RecursionError


@dataclass
class Context:
    """Data bag carried through the pipeline stages."""
    raw_input: str
    enriched_input: str = ""
    agents: list[str] = field(default_factory=list)
    messages: list = field(default_factory=list)
    response: str = ""
    formatted: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None


class Pipeline:
    """Wires six single-responsibility classes into a complete request pipeline.

    Usage:
        pipeline = Pipeline(router=router, executor=executor, ...)
        await pipeline.start()              # if using Agents.start() flow
        result = await pipeline.process("open firefox")
        print(result)

    The pipeline is stateless between calls (each process() is independent).
    History persists across calls via the History instance.
    """

    def __init__(self, *,
                 router: Router,
                 executor: Executor,
                 history: History,
                 formatter: Formatter,
                 extractor: Extractor):
        self.router = router
        self.executor = executor
        self.history = history
        self.formatter = formatter
        self.extractor = extractor
        self._context: Context | None = None

    # ── properties ──

    @property
    def last_tool_calls(self) -> list[dict]:
        """Tool calls from the most recent process() invocation."""
        if self._context:
            return self._context.tool_calls
        return []

    @property
    def context(self) -> Context | None:
        """The full pipeline context from the last run (for inspection)."""
        return self._context

    # ── main entry ──

    async def process(self, user_input: str) -> str:
        """Run the full pipeline for one user request.

        Stages:
          1. enrich  — prepend history context (History)
          2. route   — decide which agents to invoke (Router)
          3. build   — construct LangChain message list (History)
          4. execute — run agents, extract responses (Executor)
          5. format  — regex cleanup of LLM output (Formatter)
          6. store   — add turn to history (History)

        Returns the formatted final response.
        """
        ctx = Context(raw_input=user_input)

        try:
            # Stage 1: Enrich input with chat context
            ctx.enriched_input = self.history.enrich_for_routing(user_input)

            # Stage 2: Route
            ctx.agents = await self.router.route(user_input, ctx.enriched_input)

            # Stage 3: Build messages (history is a separate concern from routing enrich)
            ctx.messages = self.history.build_messages(user_input, include_history=True)

            # Stage 4: Execute agents
            result = await self.executor.execute(
                ctx.agents, ctx.messages, user_input=user_input,
                recursion_limit=cfg_recursion_limit(),
            )
            ctx.response = result.text
            ctx.tool_calls = result.tool_calls

            # Stage 5: Format
            ctx.formatted = self.formatter.format(ctx.response)

            # Stage 6: Store in history
            self.history.add_turn(user_input, ctx.formatted)
            logger.info("Done: {} chars, {} tool calls", len(ctx.formatted), len(ctx.tool_calls))

        except GraphRecursionError:
            ctx.error = "recursion_limit"
            logger.warning("Pipeline: recursion limit reached")
            ctx.formatted = (
                "I'm having trouble completing that — it took too many "
                "steps. Could you try breaking it into simpler requests?"
            )
        except Exception as exc:
            ctx.error = str(exc)
            logger.error("Pipeline error: {}", exc)
            ctx.formatted = f"I ran into a problem: {exc}"

        self._context = ctx
        return ctx.formatted
