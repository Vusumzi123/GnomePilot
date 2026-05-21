"""Chat history management — store turns, build LangChain messages, enrich for routing."""

from langchain_core.messages import HumanMessage, AIMessage


class History:
    """Manages conversation history: add turns, build message lists, provide
    enrichment context for the router.

    History is in-memory only — restarts lose context.
    """

    def __init__(self, max_turns: int = 10):
        self._turns: list[dict[str, str]] = []
        self.max_turns = max_turns

    # ── public API ──

    @property
    def turns(self) -> int:
        """Number of conversation turns currently stored."""
        return len(self._turns)

    def add_turn(self, user_input: str, response: str) -> None:
        """Append a turn and trim to max_turns (FIFO).

        No-op when max_turns <= 0.
        """
        if self.max_turns <= 0:
            return
        self._turns.append({"user": user_input, "assistant": response})
        while len(self._turns) > self.max_turns:
            self._turns.pop(0)

    def build_messages(self, user_input: str, *,
                       include_history: bool = True) -> list:
        """Build the message list for an agent invocation.

        When include_history is True and history is available, prepends
        stored turns as (HumanMessage, AIMessage) pairs so the LLM sees
        conversation context.  Always appends the current input as a
        final HumanMessage.

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
