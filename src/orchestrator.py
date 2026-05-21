import ast
import os
import re
import sys
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from loguru import logger

from src.config import (get_model, get_setting, read_prompt, unified_model,
                        formatter_enabled, num_ctx, chat_history_size,
                        debug_enabled, debug_verbose)


class Orchestrator:
    """Routes user input to the right subagent (general or vision), extracts the
    final response from LangGraph messages, and cleans it up via regex formatting.

    Two LangGraph ReAct agents operate independently:
      - general_agent: apps, packages, window management (no screenshot tool)
      - vision_agent: screenshot + visual analysis (screenshot tool only)
    """

    def __init__(self, model: str | None = None, temperature: float | None = None):
        """Resolve models from config, create ChatOllama instances, load prompts.

        If unified_model is set in config, both agents and the router share one model
        to avoid VRAM swapping. Otherwise each agent uses its own Ollama model.
        """
        model = model or get_model("orchestrator", "llama3.1:8b")
        vision_model = get_model("vision", "qwen3.5:4b")
        temperature = temperature if temperature is not None else get_setting("orchestrator.temperature", 0)
        ctx = num_ctx()

        unified = unified_model()
        if unified:
            model = vision_model = unified

        base_kwargs = {"num_ctx": ctx} if ctx else {}

        cb_kwargs = {}
        if debug_enabled():
            from src.debug import DebugCallbackHandler
            cb_kwargs = {"callbacks": [DebugCallbackHandler(verbose=debug_verbose())]}

        self.llm = ChatOllama(model=model, temperature=temperature, **base_kwargs, **cb_kwargs)
        self.vision_llm = ChatOllama(model=vision_model, temperature=temperature, **base_kwargs, **cb_kwargs)

        self.router_llm = ChatOllama(model=model, temperature=0, stop=["\n"], **base_kwargs, **cb_kwargs)

        self.formatter_enabled = formatter_enabled()

        self.router_prompt = read_prompt("router", "")
        self.general_prompt = read_prompt("general", (
            "You are a helpful AI assistant running on CachyOS (Arch Linux with GNOME). "
            "You have tools to open/close applications, search/install packages, and "
            "manage workspaces. Use them when needed. Keep responses concise and natural."
        ))
        self.vision_prompt = read_prompt("vision", (
            "Describe what's on the screen naturally. "
            "Never mention file paths, screenshots, or technical capture details."
        ))
        self.general_agent = None
        self.vision_agent = None
        self.last_tool_calls: list[dict] = []
        self.chat_history: list[dict[str, str]] = []
        self.chat_history_size = chat_history_size()

    async def initialize(self) -> None:
        """Start the MCP server, discover tools, and build both ReAct agents.

        Splits tools: vision_agent gets only tool_capture_screen; general_agent gets
        all other tools (open/close app, search/install package, move window).
        """
        client = MultiServerMCPClient(
            {
                "system_tools": {
                    "command": sys.executable,
                    "args": ["-m", "src.tools.server"],
                    "transport": "stdio",
                    "env": dict(os.environ),
                }
            }
        )
        tools = await client.get_tools()

        vision_tools = [t for t in tools if t.name == "tool_capture_screen"]
        general_tools = [t for t in tools if t.name != "tool_capture_screen"]

        self.general_agent = create_react_agent(
            self.llm,
            general_tools,
            prompt=self.general_prompt,
        )
        self.vision_agent = create_react_agent(
            self.vision_llm,
            vision_tools,
            prompt=self.vision_prompt,
        )

    async def _route(self, user_input: str) -> list[str]:
        """Decide which agent(s) to invoke — hybrid regex + LLM.

        Step 1: Regex catches obvious patterns (screen words, action words).
                When both screen + action match → chain immediately, no LLM.
        Step 2: LLM handles ambiguous queries with a simple yes/no question
                ("Is the user asking about their screen?"). Reliable on 2B+ models.

        Returns ["vision"], ["general"], or ["vision","general"] (chain).
        """
        lower = user_input.lower()

        SCREEN_WORDS = ("screen", "display", "monitor", "screenshot",
                         "what is on my", "what's on my", "what can you see",
                         "what do you see", "look at", "take a look",
                         "describe what you see", "describe my display")
        ACTION_WORDS = ("open", "close", "move", "install", "launch",
                         "start", "run", "terminate", "kill")

        has_screen = any(w in lower for w in SCREEN_WORDS)
        has_action = any(w in lower for w in ACTION_WORDS)
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

        answer = await self._llm_is_screen(lower)
        if answer:
            logger.info("Route → [vision] (LLM)")
            return ["vision"]
        logger.info("Route → [general] (LLM)")
        return ["general"]

    async def _llm_is_screen(self, user_input: str) -> bool:
        """Ask the router LLM a binary question: is this about the user's screen?"""
        if not self.router_prompt:
            return False
        try:
            logger.debug("Router LLM query: {}", self.router_prompt)
            logger.debug("Router LLM input: {}", user_input)
            msg = await self.router_llm.ainvoke([
                HumanMessage(content=f"{self.router_prompt}\n\nRequest: {user_input}")
            ])
            content = msg.content
            if isinstance(content, list):
                content = " ".join(str(c) for c in content)
            return content.strip().lower().startswith("yes")
        except Exception:
            return False

    def _extract_tool_calls(self, messages: list) -> None:
        """Walk LangGraph messages to record which tools were called and their results.

        Populates self.last_tool_calls with {name, args, result} dicts for each
        AIMessage tool call followed by a corresponding ToolMessage.
        """
        for m in messages:
            if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    self.last_tool_calls.append({
                        "name": tc["name"],
                        "args": tc["args"],
                        "result": "",
                    })
            elif isinstance(m, ToolMessage):
                for prev in reversed(self.last_tool_calls):
                    if prev["name"] and prev["result"] == "":
                        prev["result"] = m.content
                        break

    def _build_messages(self, user_input: str, include_history: bool = True) -> list:
        """Build the messages list for an agent invocation.

        Prepends previous conversation turns as (HumanMessage, AIMessage) pairs
        so the LLM sees the full chat context. Only the first agent in a chain
        gets history; subsequent chained agents receive a crafted prompt instead.
        """
        messages: list = []
        if include_history and self.chat_history and self.chat_history_size > 0:
            effective = self.chat_history[-self.chat_history_size:]
            logger.info("History: prepending {} turns (max={})", len(effective), self.chat_history_size)
            for turn in effective:
                messages.append(HumanMessage(content=turn["user"]))
                messages.append(AIMessage(content=turn["assistant"]))
        messages.append(HumanMessage(content=user_input))
        return messages

    def _add_to_history(self, user_input: str, response: str) -> None:
        """Append a turn to chat history, trimming to the configured max size."""
        if self.chat_history_size <= 0:
            return
        self.chat_history.append({"user": user_input, "assistant": response})
        while len(self.chat_history) > self.chat_history_size:
            self.chat_history.pop(0)
        logger.info("History: now {}/{} turns", len(self.chat_history), self.chat_history_size)

    async def ainvoke(self, user_input: str) -> str:
        """Route to the correct agent(s) via LLM, chain if multiple needed, and return
        the cleaned final response. Maintains conversation context across calls.

        1. Router LLM decides which agent(s) — "general", "vision", or both.
        2. Builds message list with chat history (first agent only).
        3. Runs agents sequentially; vision agent's result is fed as context to general.
        4. Extracts tool call tracking info.
        5. Pulls the final text response from the message history.
        6. Formats, stores in history, and returns.
        """
        self.last_tool_calls.clear()
        logger.info("Routing: {!r:.80}", user_input)
        agents = await self._route(user_input)

        final_response = ""
        vision_context = ""

        for i, name in enumerate(agents):
            agent = self.vision_agent if name == "vision" else self.general_agent
            is_first = (i == 0)
            logger.info("Chain step {}/{}: {} (first={})", i + 1, len(agents), name, is_first)

            if name == "general" and vision_context:
                logger.info("Chaining: injecting {} chars vision context", len(vision_context))
                prompt = (
                    f"The user asked: \"{user_input}\"\n\n"
                    f"Context from vision analysis (already completed):\n{vision_context}\n\n"
                    "Now perform the requested action using this context."
                )
                messages = [HumanMessage(content=prompt)]
            else:
                messages = self._build_messages(user_input, include_history=is_first)

            result = await agent.ainvoke(
                {"messages": messages},
                {"recursion_limit": 10},
            )

            self._extract_tool_calls(result["messages"])
            response = self._last_response(result["messages"])
            logger.info("{} agent returned {} chars", name, len(response))

            if name == "vision":
                vision_context = response

            final_response = response

        formatted = await self._format_response(final_response)
        self._add_to_history(user_input, formatted)
        logger.info("Done: {} chars, {} tool calls", len(formatted), len(self.last_tool_calls))
        return formatted

    _STRIP_RE = re.compile(
        "["
        "\U0001F300-\U0001F9FF"  # emoticons, symbols, pictographs
        "\U0001FA00-\U0001FAFF"  # symbols extended
        "\U00002600-\U000027BF"  # misc symbols (checkmarks, stars)
        "\U0000FE00-\U0000FE0F"  # variation selectors
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F680-\U0001F6FF"  # transport/map
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\u200B-\u200F"          # zero-width chars, RTL marks
        "\u2028-\u202F"          # line/paragraph separators, narrow NBSP
        "\uFEFF"                 # BOM / zero-width no-break space
        "\u00AD"                 # soft hyphen
        "\u2060-\u2064"          # word joiner, invisible chars
        "]+",
        re.UNICODE,
    )

    _TOOL_CALL_RE = re.compile(
        r'\{\s*"name"\s*:\s*"[^"]+",\s*"parameters"\s*:\s*\{[^}]*\}\s*\}'
    )

    _JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)

    async def _format_response(self, text: str) -> str:
        """Strip emojis, invisible chars, JSON fences, and leaky MCP tool-call artifacts."""
        if not self.formatter_enabled:
            return text
        try:
            cleaned = self._JSON_FENCE_RE.sub(r"\1", text)
            cleaned = self._STRIP_RE.sub("", cleaned)
            cleaned = self._TOOL_CALL_RE.sub("", cleaned)
            result = re.sub(r"\s{2,}", " ", cleaned).strip()
            if len(result) != len(text):
                logger.debug("Formatter: {} → {} chars", len(text), len(result))
            return result
        except Exception:
            return text

    def _last_response(self, messages: list) -> str:
        """Extract the final human-readable response from a LangGraph message list.

        Scans messages in reverse for the last AIMessage with real content
        (not a tool call or malformed JSON). Falls back to the last ToolMessage
        result or the final message content.
        """
        for m in reversed(messages):
            if isinstance(m, AIMessage) and not m.tool_calls and m.content.strip():
                content = m.content.strip()
                if not (content.startswith("{") and content.endswith("}")):
                    return content
                try:
                    obj = ast.literal_eval(content)
                    if "name" not in obj or "parameters" not in obj:
                        return content
                except (ValueError, SyntaxError):
                    return content
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                return self._clean_tool_result(m.content)
        return messages[-1].content if messages else ""

    def _clean_tool_result(self, content: str | list) -> str:
        """Extract human-readable text from a raw MCP tool response.

        Handles both list-of-dicts and string forms, stripping transport wrappers.
        """
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item.get("text", str(item)))
                else:
                    parts.append(str(item))
            return " ".join(parts)
        m = re.search(r"'text':\s*'([^']+)'", content)
        if m:
            return m.group(1)
        return content

    async def close(self) -> None:
        """Gracefully unload all Ollama models from VRAM on shutdown."""
        import ollama
        try:
            for m in ollama.ps().models:
                name = m.name or m.model
                if name:
                    ollama.generate(model=name, prompt="", keep_alive=0)
        except Exception:
            pass
