"""MCP Tool Server -- stdio entry point spawned by the orchestrator.

All tools are auto-discovered from sibling modules via register_all().
To add a new skill, create a .py file in this directory with a register(mcp) function.
"""

from mcp.server.fastmcp import FastMCP

from . import register_all

mcp = FastMCP("CachyOS Assistant Tools")
register_all(mcp)


def main() -> None:
    """Run the MCP server on stdio (spawned by the orchestrator as a subprocess)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
