import logging
import sys


def run_stdio(mcp) -> None:
    # IMPORTANT: stdout belongs to the MCP protocol. Log to stderr only, and never print().
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run(transport="stdio")