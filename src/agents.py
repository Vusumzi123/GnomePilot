"""Agents — LLM and LangGraph agent lifecycle management.

Creates ChatOllama instances, starts the MCP tool server, discovers tools,
builds ReAct agents, and handles graceful VRAM cleanup.
"""

import asyncio
import os
import sys

from langchain_ollama import ChatOllama
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from src.config import (get_model, get_setting, read_prompt, unified_model,
                        num_ctx, debug_enabled, debug_verbose)
from src.tools import _build_tool_list
from src.tools.vision import handler as _vision_handler
from src.tools.application import handler as _application_handler
from src.tools.package_manager import handler as _package_manager_handler
from src.tools.web_search import handler as _web_search_handler
from src.tools.window_manager import handler as _window_manager_handler


MCP_ENV_KEYS = [
    # The MCP tool server subprocess launches GUI apps via subprocess.Popen.
    # Those child processes inherit this environment. Missing keys = GUI apps
    # can't find the compositor/display and silently fail to open.
    # Trace the chain: MCP subprocess → tool function → Popen/DBus child
    # before adding or removing keys.
    "PATH",
    "HOME",
    "DBUS_SESSION_BUS_ADDRESS",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
    "XDG_CURRENT_DESKTOP",
    "LANG",
]


class Agents:
    """Manages the lifecycle of LLM instances and LangGraph ReAct agents.

    Call start() to begin the MCP tool server and build agents.
    Call restart() after config changes to reload tools without restarting
    the main process.
    Call shutdown() to unload Ollama models from VRAM.
    """

    def __init__(self, model: str | None = None,
                 vision_model: str | None = None,
                 temperature: float | None = None):
        model = model or get_model("orchestrator", "llama3.1:8b")
        vision_model = vision_model or get_model("vision", "qwen3.5:4b")
        temperature = (temperature if temperature is not None
                       else get_setting("orchestrator.temperature", 0))
        ctx = num_ctx()

        unified = unified_model()
        if unified:
            model = vision_model = unified

        base_kwargs = {"num_ctx": ctx} if ctx else {}

        cb_kwargs = {}
        if debug_enabled():
            from src.debug import DebugCallbackHandler
            cb_kwargs = {"callbacks": [DebugCallbackHandler(verbose=debug_verbose())]}

        self._general_llm = ChatOllama(model=model, temperature=temperature, **base_kwargs, **cb_kwargs)
        self._vision_llm = ChatOllama(model=vision_model, temperature=temperature, **base_kwargs, **cb_kwargs)
        self._router_llm = ChatOllama(model=model, temperature=0, stop=["\n"], **base_kwargs, **cb_kwargs)

        self.general_prompt = read_prompt("general", (
            "You are a helpful AI assistant running on CachyOS (Arch Linux with GNOME). "
        )).replace("{tool_descriptions}", _build_tool_list())
        self.vision_prompt = read_prompt("vision", (
            "Describe what's on the screen naturally. "
        ))
        self.router_prompt = read_prompt("router", "")

        self._general_agent = None
        self._vision_agent = None
        self._client = None

    # ── lifecycle ──

    async def start(self) -> None:
        """Start the MCP tool server, discover tools, and build both ReAct agents.

        Splits tools: vision agent gets only tool_capture_screen;
        general agent gets all other tools (open/close app, search/install
        package, move window).
        """
        self._client = MultiServerMCPClient(
            {
                "system_tools": {
                    "command": sys.executable,
                    "args": ["-m", "src.tools.server"],
                    "transport": "stdio",
                    "env": {k: os.environ[k] for k in MCP_ENV_KEYS
                            if k in os.environ},
                }
            }
        )
        tools = await self._client.get_tools()

        vision_tools = [t for t in tools if t.name == "tool_capture_screen"]
        general_tools = [t for t in tools if t.name != "tool_capture_screen"]

        self._general_agent = create_react_agent(
            self._general_llm, general_tools, prompt=self.general_prompt,
        )
        if not vision_tools:
            self._vision_agent = _vision_handler
        else:
            self._vision_agent = create_react_agent(
                self._vision_llm, vision_tools, prompt=self.vision_prompt,
            )

    async def restart(self) -> None:
        """Shut down and restart the MCP tool server and agents.

        Call after updating config.json (e.g., toggling skills) to apply
        changes without restarting the entire process.
        """
        self._client = None
        await asyncio.sleep(0.3)
        await self.shutdown()
        await self.start()

    async def shutdown(self) -> None:
        """Gracefully unload all Ollama models from VRAM."""
        import ollama
        try:
            for m in ollama.ps().models:
                name = m.name or m.model
                if name:
                    ollama.generate(model=name, prompt="", keep_alive=0)
        except Exception:
            pass

    # ── properties ──

    @property
    def general(self):
        """The general agent (apps, packages, windows)."""
        return self._general_agent

    @property
    def vision(self):
        """The vision agent (screenshot + analysis)."""
        return self._vision_agent

    @property
    def general_llm(self) -> ChatOllama:
        """The LLM instance used by the general agent (reusable by Router)."""
        return self._general_llm
