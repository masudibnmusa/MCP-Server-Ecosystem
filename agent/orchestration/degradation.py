"""What to do when a server is down or a call fails. Rules:

- Call never started (server down): wait briefly for a reconnect, then retry once. Safe for writes.
- Read-only tool timed out / connection dropped: wait for reconnect and retry once.
- WRITE tool timed out / connection dropped: NEVER retry automatically (could duplicate the
  action). Tell the model the outcome is unknown so it verifies first.
- Otherwise return an LLM-readable error so the agent can skip that part and tell the user.
"""
import asyncio

from agent.mcp_client.capability_loader import ToolInfo
from agent.mcp_client.tool_router import (
    ConnectionLost,
    ServerUnavailable,
    ToolPermissionError,
    ToolResult,
    ToolRouter,
    ToolTimeout,
)


class DegradationPolicy:
    def __init__(self, router: ToolRouter, manager, reconnect_wait_s: float = 6.0, read_retries: int = 1):
        self.router = router
        self.manager = manager
        self.reconnect_wait_s = reconnect_wait_s
        self.read_retries = read_retries

    def unavailable_servers(self) -> list[str]:
        return [n for n, c in self.manager.connections.items() if c.state != "up"]

    async def _wait_until_up(self, server: str) -> bool:
        conn = self.manager.connections.get(server)
        if conn is None:
            return False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.reconnect_wait_s
        while loop.time() < deadline:
            if conn.state == "up":
                return True
            await asyncio.sleep(0.25)
        return conn.state == "up"

    async def call(self, info: ToolInfo, arguments: dict) -> ToolResult:
        attempts = 0
        while True:
            try:
                return await self.router.call(info, arguments)

            except ToolPermissionError as e:
                return ToolResult(str(e), True)

            except ServerUnavailable:
                if attempts < 1 and await self._wait_until_up(info.server):
                    attempts += 1
                    continue
                return ToolResult(
                    f"The '{info.server}' server is unavailable right now, so {info.namespaced} could "
                    "not run. Do not retry. Skip this part, continue with what you can, and tell the "
                    "user which part of their request was not completed.",
                    True,
                )

            except (ToolTimeout, ConnectionLost) as e:
                if info.read_only:
                    if attempts < self.read_retries and await self._wait_until_up(info.server):
                        attempts += 1
                        continue
                    return ToolResult(f"{e} Do not retry. Tell the user this lookup failed.", True)
                return ToolResult(
                    f"{e} The outcome is UNKNOWN: the action may or may not have been applied. "
                    "Verify with a read-only tool before trying again, and never repeat a write blindly.",
                    True,
                )