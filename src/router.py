"""Router — hybrid regex + LLM routing to decide which agent(s) to invoke."""

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from loguru import logger


class Router:
    """Decides which agents (general, vision, or both in chain) should handle
    a user request.

    Uses a two-tier strategy:
    1. Regex fast-path for obvious screen/action keywords in the ORIGINAL input.
    2. LLM fallback for ambiguous queries using the enriched input (which may
       include history context).
    """

    SCREEN_WORDS = (
        "screen", "display", "monitor", "screenshot",
        "what is on my", "what's on my", "what can you see",
        "what do you see", "look at", "take a look",
        "describe what you see", "describe my display",
    )

    ACTION_WORDS = (
        "open", "close", "move", "install", "launch",
        "start", "run", "terminate", "kill",
    )

    def __init__(self, llm: ChatOllama, prompt: str = ""):
        self.llm = llm
        self.prompt = prompt

    async def route(self, user_input: str, enriched: str = "") -> list[str]:
        """Decide which agent(s) to invoke.

        Regex runs on the ORIGINAL input only — no history contamination.
        LLM fallback receives the enriched input with history context.

        Returns ["vision"], ["general"], or ["vision", "general"] (chain).
        """
        lower = user_input.lower()

        has_screen = any(w in lower for w in self.SCREEN_WORDS)
        has_action = any(w in lower for w in self.ACTION_WORDS)
        logger.debug("Router (regex): screen={}, action={}", has_screen, has_action)

        if has_screen and has_action:
            logger.info("Route → [vision, general] (chain)")
            return ["vision", "general"]
        if has_screen and not has_action:
            logger.info("Route → [vision]")
            return ["vision"]
        if has_action and not has_screen:
            logger.info("Route → [general]")
            return ["general"]

        llm_input = enriched or user_input
        answer = await self._llm_is_screen(llm_input)
        if answer:
            logger.info("Route → [vision] (LLM)")
            return ["vision"]
        logger.info("Route → [general] (LLM)")
        return ["general"]

    async def _llm_is_screen(self, user_input: str) -> bool:
        """Ask the router LLM a binary yes/no: is this about the user's screen?"""
        if not self.prompt:
            return False
        try:
            logger.debug("Router LLM query: {}", self.prompt)
            logger.debug("Router LLM input: {}", user_input)
            msg = await self.llm.ainvoke([
                HumanMessage(content=f"{self.prompt}\n\nRequest: {user_input}")
            ])
            content = msg.content
            if isinstance(content, list):
                content = " ".join(str(c) for c in content)
            return content.strip().lower().startswith("yes")
        except Exception:
            return False
