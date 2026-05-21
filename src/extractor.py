"""Response extraction — pull text and tool-call data from LangGraph messages."""

import ast
import re

from langchain_core.messages import AIMessage, ToolMessage


class Extractor:
    """Static utilities for extracting the final human-readable response and
    tool-call tracking data from a LangGraph message list.
    """

    @staticmethod
    def response(messages: list) -> str:
        """Return the final text from a LangGraph message list.

        Scans messages in reverse for the last AIMessage with real content
        (not a tool call or malformed JSON).  Falls back to the last
        ToolMessage result or the raw final message content.
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
                return Extractor.clean_result(m.content)

        return messages[-1].content if messages else ""

    @staticmethod
    def tool_calls(messages: list) -> list[dict]:
        """Walk messages and return [{name, args, result}, ...] per tool call.

        Pairs AIMessage tool_call entries with their corresponding ToolMessage
        results by walking forward and storing the result of the first
        unmatched tool call encountered.
        """
        calls: list[dict] = []
        for m in messages:
            if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    calls.append({
                        "name": tc["name"],
                        "args": tc["args"],
                        "result": "",
                    })
            elif isinstance(m, ToolMessage):
                for prev in reversed(calls):
                    if prev["name"] and prev["result"] == "":
                        prev["result"] = m.content
                        break
        return calls

    @staticmethod
    def clean_result(content) -> str:
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
        if isinstance(content, str):
            m = re.search(r"'text':\s*'([^']+)'", content)
            if m:
                return m.group(1)
        return str(content)
