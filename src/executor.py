"""Executor — runs agents sequentially with chaining support."""

from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage
from loguru import logger

from src.extractor import Extractor


@dataclass
class AgentResult:
    """Result of an agent execution run."""
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    vision_context: str = ""


class Executor:
    """Runs a list of agents in order, supporting chaining where vision output
    is injected as context into the general agent.
    """

    def __init__(self, agents):
        from src.agents import Agents
        self._agents: Agents = agents
        self.last_tool_calls: list[dict] = []

    async def execute(self, agents_order: list[str], messages: list, *,
                      vision_context: str = "", user_input: str = "",
                      recursion_limit: int = 10) -> AgentResult:
        """Execute the given agents in sequence.

        For a chain ["vision", "general"]:
          - Vision agent runs first with the provided messages.
          - Its response becomes vision_context.
          - General agent runs second with a crafted prompt containing
            the vision analysis, NOT the original messages.

        Args:
            agents_order: Agent names to run (e.g. ["vision"] or ["vision","general"]).
            messages: Pre-built LangChain message list for the first agent.
            vision_context: Existing vision analysis (used when resuming a chain).
            user_input: Original user request (used for chaining prompt).
            recursion_limit: Max LangGraph recursion steps per agent.
        """
        self.last_tool_calls.clear()
        final_text = ""

        for i, name in enumerate(agents_order):
            agent = self._agents.vision if name == "vision" else self._agents.general
            is_first = (i == 0)
            logger.info("Chain step {}/{}: {} (first={})", i + 1, len(agents_order), name, is_first)

            if name == "general" and vision_context:
                logger.info("Chaining: injecting {} chars vision context", len(vision_context))
                prompt = (
                    f"The user asked: \"{user_input}\"\n\n"
                    f"Context from vision analysis (already completed):\n{vision_context}\n\n"
                    "Now perform the requested action using this context."
                )
                current_messages = [HumanMessage(content=prompt)]
            else:
                current_messages = messages

            result = await agent.ainvoke(
                {"messages": current_messages},
                {"recursion_limit": recursion_limit},
            )

            raw_messages = result["messages"]
            self.last_tool_calls.extend(Extractor.tool_calls(raw_messages))
            response = Extractor.response(raw_messages)
            logger.info("{} agent returned {} chars", name, len(response))

            if name == "vision":
                vision_context = response

            final_text = response

        return AgentResult(text=final_text, tool_calls=list(self.last_tool_calls),
                           vision_context=vision_context)
