"""Namespaced tool name -> owning server. Also enforces permissions and handles timeouts.

Failure handling policy (retries, waiting for reconnects) lives in orchestration/degradation.py.
"""
import asyncio
from dataclasses import dataclass

from mcp.shared.exceptions import McpError

from agent.config import AgentConfig
from security.permissions import Permissions

from .capability_loader import ToolInfo
from .connection_manager import ConnectionManager, ServerUnavailable
from .namespace import NamespaceError, split_name

__all__ = ["ToolRouter", "ToolResult", "ServerUnavailable", "ToolTimeout", "ConnectionLost", "ToolPermissionError"]


class ToolTimeout(Exception):
    pass


class ConnectionLost(Exception):
    pass


class ToolPermissionError(Exception):
    pass


@dataclass
class ToolResult:
    text: str
    is_error: bool = False


def _flatten(content) -> str:
    parts = []
    for block in content or []:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else f"[{getattr(block, 'type', 'unknown')} content omitted]")
    return "\n".join(parts)


class ToolRouter:
    def __init__(self, manager: ConnectionManager, permissions: Permissions, cfg: AgentConfig):
        self.manager = manager
        self.permissions = permissions
        self.cfg = cfg

    def tools(self) -> list[ToolInfo]:
        """Tools the LLM may use right now: server is up AND permissions allow it."""
        out: list[ToolInfo] = []
        for conn in self.manager.connections.values():
            if conn.state != "up" or conn.capabilities is None:
                continue
            for t in conn.capabilities.tools:
                if self.permissions.is_allowed(conn.spec.name, t.name):
                    out.append(t)
        return out

    def resolve(self, namespaced: str) -> ToolInfo | None:
        """Look up a tool even if its server is down, so degradation can decide what to do."""
        try:
            server, tool = split_name(namespaced)
        except NamespaceError:
            return None
        conn = self.manager.connections.get(server)
        if conn is None or conn.capabilities is None:
            return None
        info = conn.capabilities.tool(tool)
        if info and self.permissions.is_allowed(server, tool):
            return info
        return None

    async def call(self, info: ToolInfo, arguments: dict) -> ToolResult:
        if not self.permissions.is_allowed(info.server, info.name):
            raise ToolPermissionError(f"Tool {info.namespaced} is not permitted by the registry rules.")

        conn = self.manager.connections.get(info.server)
        if conn is None or conn.state != "up" or conn.session is None:
            raise ServerUnavailable(info.server, conn.last_error or "" if conn else "")

        timeout = conn.spec.call_timeout_s or self.cfg.call_timeout_s
        try:
            res = await asyncio.wait_for(conn.session.call_tool(info.name, arguments), timeout)
        except asyncio.TimeoutError:
            conn.mark_lost(f"{info.namespaced} timed out after {timeout}s")  # restart a stuck server
            raise ToolTimeout(f"{info.namespaced} timed out after {timeout}s")
        except McpError as e:
            return ToolResult(f"The server rejected the call: {e}", True)
        except Exception as e:
            conn.mark_lost(f"connection error during {info.namespaced}")
            raise ConnectionLost(f"Connection to '{info.server}' was lost during the call ({type(e).__name__}).") from e

        return ToolResult(_flatten(res.content), bool(res.isError))