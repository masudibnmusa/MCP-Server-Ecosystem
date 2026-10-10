"""Calendar MCP server.

    python -m servers.calendar_server.server
"""
from mcp.server.fastmcp import FastMCP

from servers.transport import main

from . import prompts, resources, tools

mcp = FastMCP(
    "calendar",
    instructions="Read a calendar, find free slots, and create events. "
    "Always call find_free_slots before create_event.",
)

tools.register(mcp)
resources.register(mcp)
prompts.register(mcp)

if __name__ == "__main__":
    main(mcp, default_port=8082)