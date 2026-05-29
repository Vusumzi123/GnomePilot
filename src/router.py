"""Router — hybrid regex + LLM routing to decide which agent(s) to invoke."""

import asyncio

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from loguru import logger


class Router:
    """Decides which agents (general, vision, or both in chain) should handle
    a user request.

    Uses a two-tier strategy:
    1. Regex fast-path for obvious screen/action keywords in the input.
    2. LLM fallback for ambiguous queries using only the current input
       (no history contamination — routing is stateless per-request).
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

    def __init__(self, llm: ChatOllama, prompt: str = "", timeout: int = 15):
        self.llm = llm
        self.prompt = prompt
        self._timeout = timeout

    async def route(self, user_input: str) -> list[str]:
        """Decide which agent(s) to invoke.

        Regex fast-path runs on the input. LLM fallback receives only
        the current user input — no history contamination.

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

        answer = await self._llm_is_screen(user_input)
        if answer:
            logger.info("Route → [vision] (LLM)")
            return ["vision"]
        logger.info("Route → [general] (LLM)")
        return ["general"]

    async def _llm_is_screen(self, user_input: str) -> bool:
        """Ask the router LLM a binary yes/no: is this about the user's screen?

        Wrapped with asyncio.wait_for — on timeout, falls back to False
        (route to general) rather than hanging the pipeline.
        """
        if not self.prompt:
            return False
        try:
            logger.debug("Router LLM query: {}", self.prompt)
            logger.debug("Router LLM input: {}", user_input)
            msg = await asyncio.wait_for(
                self.llm.ainvoke([
                    HumanMessage(content=f"{self.prompt}\n\nRequest: {user_input}")
                ]),
                timeout=self._timeout,
            )
            content = msg.content
            if isinstance(content, list):
                content = " ".join(str(c) for c in content)
            return content.strip().lower().startswith("yes")
        except asyncio.TimeoutError:
            logger.warning("Router LLM timeout ({}s) — falling back to general", self._timeout)
            return False
        except Exception:
            return False
