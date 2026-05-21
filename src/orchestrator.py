import ast
import os
import re
import sys
from pathlib import Path

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from src.config import get_model, get_setting, read_prompt, unified_model, formatter_enabled


VISION_KEYWORDS = [
    r"screen", r"see", r"display", r"monitor", r"screenshot",
    r"what.*on", r"show", r"look", r"visible", r"desktop",
    r"what.*see", r"on my screen",
]


class Orchestrator:
    """Routes user input to the right subagent (general or vision), extracts the
    final response from LangGraph messages, and cleans it up via regex formatting.

    Two LangGraph ReAct agents operate independently:
      - general_agent: apps, packages, window management (no screenshot tool)
      - vision_agent: screenshot + visual analysis (screenshot tool only)
    """

    def __init__(self, model: str | None = None, temperature: float | None = None):
        """Resolve models from config, create ChatOllama instances, load prompts.

        If unified_model is set in config, both agents share one model to avoid
        VRAM swapping. Otherwise each agent uses its own Ollama model.
        """
        model = model or get_model("orchestrator", "llama3.1:8b")
        vision_model = get_model("vision", "qwen3.5:4b")
        temperature = temperature if temperature is not None else get_setting("orchestrator.temperature", 0)

        unified = unified_model()
        if unified:
            model = vision_model = unified

        self.llm = ChatOllama(model=model, temperature=temperature)
        self.vision_llm = ChatOllama(model=vision_model, temperature=temperature)

        self.formatter_enabled = formatter_enabled()

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

    def _is_vision_request(self, text: str) -> bool:
        """Check whether the user input matches vision-related keywords."""
        return any(re.search(p, text.lower()) for p in VISION_KEYWORDS)

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

    async def ainvoke(self, user_input: str) -> str:
        """Route user input to the correct agent, run it, and return the cleaned response.

        1. Picks vision_agent if input matches vision keywords, else general_agent.
        2. Invokes the selected LangGraph ReAct agent.
        3. Extracts tool call tracking info.
        4. Pulls the final text response from the message history.
        5. Passes it through the regex formatter.
        """
        self.last_tool_calls.clear()

        agent = self.vision_agent if self._is_vision_request(user_input) else self.general_agent

        result = await agent.ainvoke({
            "messages": [HumanMessage(content=user_input)]
        })

        self._extract_tool_calls(result["messages"])
        response = self._last_response(result["messages"])
        return await self._format_response(response)

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

    async def _format_response(self, text: str) -> str:
        """Strip emojis, invisible chars, and leaky MCP tool-call artifacts via regex."""
        if not self.formatter_enabled:
            return text
        try:
            cleaned = self._STRIP_RE.sub("", text)
            cleaned = self._TOOL_CALL_RE.sub("", cleaned)
            return re.sub(r"\s{2,}", " ", cleaned).strip()
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
