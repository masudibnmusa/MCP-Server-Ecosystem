"""Internal tools MCP server (tickets, wiki, chat). Runs well over streamable HTTP.

    python -m servers.internal_tools_server.server                              # stdio
    python -m servers.internal_tools_server.server --transport http --port 8080
"""
from mcp.server.fastmcp import FastMCP

from servers.transport import main

from . import resources, tools

mcp = FastMCP(
    "internal_tools",
    instructions="Create tickets, search the wiki, and post to chat. "
    "create_ticket and post_to_chat make changes and require approval.",
)

tools.register(mcp)
resources.register(mcp)

if __name__ == "__main__":
    main(mcp, default_port=8080)