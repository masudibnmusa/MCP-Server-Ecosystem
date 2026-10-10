"""Start, hold, and reconnect to MCP servers.

Each server gets ONE long-lived task. MCP transports use anyio task groups, which must be
entered and exited from the same task, so that task opens the transport, holds the session,
and closes everything itself. If the link dies, the task reconnects with exponential backoff.

If your installed `mcp` SDK renamed `streamablehttp_client`, adjust the import below.
"""
import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from typing import Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from pydantic import AnyUrl

from agent.config import AgentConfig
from registry.registry_loader import ServerSpec
from security.secrets_manager import get_secret

from .capability_loader import Capabilities, load_capabilities
from .health import HealthMonitor

log = logging.getLogger("mcp.connection")

StateCallback = Callable[[str, str, "str | None"], None]


class ServerUnavailable(Exception):
    def __init__(self, server: str, detail: str = ""):
        self.server = server
        super().__init__(f"Server '{server}' is unavailable. {detail}".strip())


def _short(exc: BaseException) -> str:
    while getattr(exc, "exceptions", None):  # unwrap ExceptionGroup
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"[:300]


class ServerConnection:
    def __init__(self, spec: ServerSpec, cfg: AgentConfig, on_state: StateCallback | None = None):
        self.spec = spec
        self.cfg = cfg
        self.on_state = on_state
        self.session: ClientSession | None = None
        self.capabilities: Capabilities | None = None  # kept after a drop, refreshed on reconnect
        self.state = "connecting"  # connecting | up | down | stopped
        self.last_error: str | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._lost = asyncio.Event()
        self._task: asyncio.Task | None = None

    # ---- lifecycle -------------------------------------------------------------------
    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name=f"mcp-{self.spec.name}")
        try:
            await asyncio.wait_for(self._ready.wait(), self.cfg.connect_timeout_s * 2 + 5)
        except asyncio.TimeoutError:
            pass

    async def stop(self) -> None:
        self._stop.set()
        self._lost.set()  # wake the waiter
        if self._task:
            try:
                await asyncio.wait_for(self._task, 10)
            except Exception:
                pass

    def mark_lost(self, reason: str) -> None:
        """Called by the router or health monitor when the link looks dead."""
        if self.state == "up":
            self.last_error = reason
            self._set_state("down", reason)  # immediately, so callers stop using the old session
            self._lost.set()

    # ---- internals -------------------------------------------------------------------
    def _set_state(self, state: str, error: str | None = None) -> None:
        if state != self.state:
            self.state = state
            if self.on_state:
                self.on_state(self.spec.name, state, error)

    async def _open_transport(self, stack: AsyncExitStack):
        spec = self.spec
        if spec.transport == "stdio":
            command = sys.executable if spec.command in ("python", "python3") else spec.command
            env = {n: v for n in spec.env_vars if (v := get_secret(n))} or None
            params = StdioServerParameters(
                command=command, args=list(spec.args), env=env, cwd=str(self.cfg.root)
            )
            read, write = await stack.enter_async_context(stdio_client(params))
            return read, write

        headers: dict[str, str] = {}
        if spec.auth_env:
            headers["Authorization"] = f"Bearer {get_secret(spec.auth_env, required=True)}"
        read, write, _ = await stack.enter_async_context(streamablehttp_client(spec.url, headers=headers))
        return read, write

    async def _wait_for_stop_or_loss(self) -> None:
        stop = asyncio.ensure_future(self._stop.wait())
        lost = asyncio.ensure_future(self._lost.wait())
        try:
            await asyncio.wait({stop, lost}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
            lost.cancel()

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), seconds)
        except asyncio.TimeoutError:
            pass

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with AsyncExitStack() as stack:
                    read, write = await self._open_transport(stack)
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await asyncio.wait_for(session.initialize(), self.cfg.connect_timeout_s)
                    self.capabilities = await asyncio.wait_for(
                        load_capabilities(self.spec, session), self.cfg.connect_timeout_s
                    )
                    self.session = session
                    self.last_error = None
                    self._lost.clear()
                    self._set_state("up")
                    backoff = 1.0
                    self._ready.set()
                    await self._wait_for_stop_or_loss()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # includes ExceptionGroup raised by anyio task groups
                self.last_error = _short(e)
                log.warning("Connection to %s failed: %s", self.spec.name, self.last_error)
            finally:
                self.session = None

            if self._stop.is_set():
                break
            self._set_state("down", self.last_error)
            self._ready.set()  # unblock start() even when the first attempt failed
            await self._sleep_or_stop(backoff)
            backoff = min(backoff * 2, 30.0)

        self._set_state("stopped")


class ConnectionManager:
    def __init__(self, specs: list[ServerSpec], cfg: AgentConfig, on_state: StateCallback | None = None):
        self.cfg = cfg
        self.connections: dict[str, ServerConnection] = {
            s.name: ServerConnection(s, cfg, on_state) for s in specs
        }
        self.health = HealthMonitor(self, cfg.health_interval_s, cfg.ping_timeout_s)

    async def __aenter__(self) -> "ConnectionManager":
        await asyncio.gather(*(c.start() for c in self.connections.values()))
        await self.health.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.health.stop()
        await asyncio.gather(*(c.stop() for c in self.connections.values()))

    def status(self) -> list[dict]:
        out = []
        for name, c in self.connections.items():
            caps = c.capabilities
            out.append(
                {
                    "name": name,
                    "state": c.state,
                    "transport": c.spec.transport,
                    "tools": len(caps.tools) if caps else 0,
                    "resources": len(caps.resources) if caps else 0,
                    "prompts": len(caps.prompts) if caps else 0,
                    "error": c.last_error,
                }
            )
        return out

    def _up(self, server: str) -> ServerConnection:
        conn = self.connections.get(server)
        if conn is None:
            raise KeyError(f"Unknown server '{server}'. Known: {', '.join(self.connections)}")
        if conn.state != "up" or conn.session is None:
            raise ServerUnavailable(server, conn.last_error or "")
        return conn

    async def read_resource(self, server: str, uri: str) -> str:
        conn = self._up(server)
        res = await asyncio.wait_for(conn.session.read_resource(AnyUrl(uri)), self.cfg.call_timeout_s)
        return "\n".join(getattr(c, "text", "") or "" for c in res.contents)

    async def get_prompt(self, server: str, name: str, arguments: dict[str, str]) -> str:
        conn = self._up(server)
        res = await asyncio.wait_for(conn.session.get_prompt(name, arguments), self.cfg.call_timeout_s)
        parts = [getattr(m.content, "text", "") for m in res.messages]
        return "\n\n".join(p for p in parts if p)