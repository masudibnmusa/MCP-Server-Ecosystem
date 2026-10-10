"""Shared entry point so every server supports stdio AND streamable HTTP.

    python -m servers.database_server.server                          # stdio
    python -m servers.database_server.server --transport http --port 8081
"""
import argparse


def main(mcp, default_port: int = 8000) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()

    if args.transport == "stdio":
        from .stdio_runner import run_stdio

        run_stdio(mcp)
    else:
        from .http_runner import run_http

        run_http(mcp, args.host, args.port)