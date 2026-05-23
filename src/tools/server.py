"""MCP Tool Server -- stdio entry point spawned by the Agents class.

All tools are auto-discovered from sibling modules via register_all(),
which respects the `skills` section of config.json.

To add a new skill, create a .py file with @tool() decorators and a
companion .toml manifest.  Toggle skills via `skills.<name>` in config.json.
"""

from mcp.server.fastmcp import FastMCP

from src.config import debug_enabled, debug_verbose, debug_log_dir, \
                       debug_retention_days, debug_rotation
from . import register_all

mcp = FastMCP("CachyOS Assistant Tools")
register_all(mcp)


def reload_tools() -> None:
    """Clear all registered tools and re-discover from config.

    Reads the current `skills` section from config.json and re-runs
    register_all().  Designed for future API-driven config changes —
    call this after updating skills in config.json to apply without
    restarting the MCP subprocess.
    """
    for tool in mcp._tool_manager.list_tools():
        mcp.remove_tool(tool.name)
    register_all(mcp)


def main() -> None:
    """Run the MCP server on stdio (spawned by the Agents class as a subprocess)."""
    if debug_enabled():
        from src.debug import configure
        configure(
            verbose=debug_verbose(),
            log_dir=debug_log_dir(),
            retention_days=debug_retention_days(),
            rotation=debug_rotation(),
        )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
