"""Streamable HTTP runner with bearer auth.

    python -m servers.transport.http_runner --server internal_tools --port 8080
"""
import argparse
import importlib

import uvicorn

from .http_auth import BearerAuthMiddleware

SERVERS = {
    "database": "servers.database_server.server",
    "calendar": "servers.calendar_server.server",
    "internal_tools": "servers.internal_tools_server.server",
}


def run_http(mcp, host: str = "127.0.0.1", port: int = 8000) -> None:
    app = mcp.streamable_http_app()  # MCP endpoint is served at /mcp
    app.add_middleware(BearerAuthMiddleware)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", choices=SERVERS, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    module = importlib.import_module(SERVERS[args.server])
    run_http(module.mcp, args.host, args.port)