"""Agents — LLM and LangGraph agent lifecycle management.

Creates LLM instances via the model factory, starts the MCP tool server,
discovers tools, builds ReAct agents, and handles graceful VRAM cleanup.
"""

import asyncio
import os
import sys

from langchain_core.language_models import BaseChatModel
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from src.config import (get_setting, read_prompt, num_ctx,
                        model_config, unified_model_config,
                        debug_enabled, debug_verbose)
from src.model_factory import create_llm
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

    def __init__(self, **kwargs):
        # Config-driven LLM creation: model, vision_model, temperature
        # params are ignored (kept as **kwargs for backward compat).

        unified = unified_model_config()
        if unified is not None:
            llm_cfg = vision_cfg = router_cfg = dict(unified)
        else:
            llm_cfg = model_config("orchestrator")
            vision_cfg = model_config("vision")
            router_cfg = model_config("router")

        # Inherit global defaults for keys not specified per-role
        global_temp = get_setting("orchestrator.temperature", 0)
        global_ctx = num_ctx()

        for cfg in (llm_cfg, vision_cfg, router_cfg):
            if "temperature" not in cfg:
                cfg["temperature"] = global_temp
            if "num_ctx" not in cfg and global_ctx is not None:
                cfg["num_ctx"] = global_ctx

        # Router gets strict stop tokens (overrides any per-role value)
        router_cfg = {**router_cfg, "temperature": 0, "stop": ["\n"]}

        # Track which providers are in use (for shutdown decisions)
        self._active_providers: set[str] = {
            llm_cfg.get("provider", "ollama"),
            vision_cfg.get("provider", "ollama"),
            router_cfg.get("provider", "ollama"),
        }

        # Build callbacks if debug is enabled
        callbacks = None
        if debug_enabled():
            from src.debug import DebugCallbackHandler
            callbacks = [DebugCallbackHandler(verbose=debug_verbose())]

        self._general_llm = create_llm(llm_cfg, callbacks=callbacks)
        self._vision_llm = create_llm(vision_cfg, callbacks=callbacks)
        self._router_llm = create_llm(router_cfg, callbacks=callbacks)

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
        """Gracefully unload Ollama models from VRAM if any role uses Ollama."""
        if "ollama" not in self._active_providers:
            return
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
    def general_llm(self) -> BaseChatModel:
        """The LLM instance used by the general agent (reusable by Router)."""
        return self._general_llm
