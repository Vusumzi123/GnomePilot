"""Chat history management — store turns, build LangChain messages, enrich for routing."""

from langchain_core.messages import HumanMessage, AIMessage


class History:
    """Manages conversation history: add turns, build message lists, provide
    enrichment context for the router.

    Trims history by both turn count (max_turns) and estimated token count
    (max_tokens). The stricter limit wins.  At least 1 turn is always retained
    when history is enabled, even if it exceeds the token budget.

    History is in-memory only — restarts lose context.
    """

    def __init__(self, max_turns: int = 10, max_tokens: int = 2000):
        self._turns: list[dict[str, str]] = []
        self.max_turns = max_turns
        self.max_tokens = max_tokens

    # ── helpers ──

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Approximate token count: ~4 chars per token for English text."""
        return max(1, len(text) // 4)

    def _trim_to_budget(self):
        """Remove oldest turns until within both turn and token budgets.

        At least 1 turn is always retained when history is enabled, even
        if a single turn exceeds the token budget.
        """
        if self.max_turns <= 0:
            self._turns.clear()
            return
        if self.max_tokens <= 0:
            self._turns.clear()
            return

        while len(self._turns) > 0:
            total = sum(
                self._estimate_tokens(t["user"]) + self._estimate_tokens(t["assistant"])
                for t in self._turns
            )
            within_turns = len(self._turns) <= self.max_turns
            within_tokens = total <= self.max_tokens

            if within_turns and within_tokens:
                break

            # Keep at least 1 turn — stop popping before emptying
            if len(self._turns) == 1:
                break

            self._turns.pop(0)

    # ── public API ──

    @property
    def turns(self) -> int:
        """Number of conversation turns currently stored."""
        return len(self._turns)

    def add_turn(self, user_input: str, response: str) -> None:
        """Append a turn and trim to limits (FIFO — oldest first).

        No-op when max_turns <= 0.  After appending, trims by both
        max_turns and max_tokens budgets (whichever is stricter).
        """
        if self.max_turns <= 0:
            return
        self._turns.append({"user": user_input, "assistant": response})
        self._trim_to_budget()

    def build_messages(self, user_input: str, *,
                       include_history: bool = True) -> list:
        """Build the message list for an agent invocation.

        When include_history is True and history is available, prepends
        stored turns as typed (HumanMessage, AIMessage) pairs so the LLM
        sees conversation context.  No preamble is injected — the system
        prompt handles behavior rules like "do not repeat prior tool calls."

        Always appends the current input as a final HumanMessage.

        Args:
            user_input: The current user request.
            include_history: If False, only the current input is included
               (used for chained agents that get a crafted prompt instead).
        """
        messages: list = []
        if include_history and self._turns and self.max_turns > 0:
            for turn in self._turns[-self.max_turns:]:
                messages.append(HumanMessage(content=turn["user"]))
                messages.append(AIMessage(content=turn["assistant"]))
        messages.append(HumanMessage(content=user_input))
        return messages

    def enrich_for_routing(self, user_input: str) -> str:
        """Prepend recent chat context so the router can resolve ambiguous
        references (e.g. "describe it again" after a vision turn).

        Concatenates the last 3 user queries into a [History: ...] prefix.
        When history is empty or disabled, returns the input unchanged.

        .. deprecated:: 2026-05
            The pipeline no longer uses this — routing is stateless and
            operates on raw user input only.  The method remains for
            backward compat but should not be used in new code.
        """
        if not self._turns or self.max_turns <= 0:
            return user_input
        last = self._turns[-3:]
        snippets = [t["user"][:80].replace("\n", " ") for t in last]
        ctx = " | ".join(snippets)
        return f"[History: {ctx}] User: {user_input}"

    def clear(self) -> None:
        """Reset history (e.g., on a fresh session)."""
        self._turns.clear()
