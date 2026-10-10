"""Heartbeat: ping every connected server; two failures in a row marks it lost so the
connection manager tears it down and reconnects."""
import asyncio
import logging
from collections import defaultdict

log = logging.getLogger("mcp.health")


class HealthMonitor:
    def __init__(self, manager, interval_s: float = 10.0, ping_timeout_s: float = 5.0, max_failures: int = 2):
        self.manager = manager
        self.interval_s = interval_s
        self.ping_timeout_s = ping_timeout_s
        self.max_failures = max_failures
        self._failures: dict[str, int] = defaultdict(int)
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="mcp-health")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.interval_s)
            await asyncio.gather(*(self._check(c) for c in list(self.manager.connections.values())))

    async def _check(self, conn) -> None:
        name = conn.spec.name
        if conn.state != "up" or conn.session is None:
            self._failures[name] = 0
            return
        try:
            await asyncio.wait_for(conn.session.send_ping(), self.ping_timeout_s)
            self._failures[name] = 0
        except Exception:
            self._failures[name] += 1
            log.warning("Health check failed for %s (%d)", name, self._failures[name])
            if self._failures[name] >= self.max_failures:
                self._failures[name] = 0
                conn.mark_lost("health check failed")