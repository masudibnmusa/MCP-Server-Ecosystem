"""Chat / CLI entry point.

    python -m agent.main                      # interactive chat
    python -m agent.main "your request"       # one-shot
    python -m agent.main --auto-approve ...   # DEMO ONLY: skips approval prompts

Chat commands: /tools  /servers  /prompts  /prompt <server> <name> [k=v ...]  /quit
"""
import argparse
import asyncio
import logging
import shlex
import sys

from agent.config import load_config
from agent.llm.llm_client import LLMClient
from agent.mcp_client.connection_manager import ConnectionManager
from agent.mcp_client.tool_router import ToolRouter
from agent.observability.call_logger import CallLogger
from agent.orchestration.agent_loop import AgentLoop
from agent.orchestration.approval_gate import ApprovalGate
from agent.orchestration.degradation import DegradationPolicy
from agent.orchestration.planner import Planner
from agent.orchestration.tool_selector import ToolSelector
from registry.registry_loader import RegistryError, load_registry
from security.permissions import Permissions
from security.secrets_manager import MissingSecretError


async def collect_schema_context(manager: ConnectionManager) -> str:
    """Auto-include any `schema://...` resource from TRUSTED servers as reference context."""
    chunks: list[str] = []
    for name, conn in manager.connections.items():
        if conn.state != "up" or conn.capabilities is None or not conn.spec.trusted:
            continue
        for res in conn.capabilities.resources:
            if res["uri"].startswith("schema://"):
                try:
                    text = await manager.read_resource(name, res["uri"])
                    chunks.append(f"[{name} {res['uri']}]\n{text[:6000]}")
                except Exception:
                    pass
    return "\n\n".join(chunks)


def print_status(manager: ConnectionManager, router: ToolRouter) -> None:
    print(f"\nMCP agent ready. {len(router.tools())} tools available.")
    for s in manager.status():
        if s["state"] == "up":
            print(f"  ✓ {s['name']:10} {s['transport']:5} {s['tools']} tools, {s['resources']} resources, {s['prompts']} prompts")
        else:
            print(f"  ✗ {s['name']:10} {s['transport']:5} {s['state']}: {s['error']}")
    print("Type a request, or /tools /servers /prompts /prompt /quit")


async def run_task(agent: AgentLoop, task: str) -> None:
    try:
        answer = await agent.run(task)
        print(f"\n{answer}")
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")


async def expand_prompt(manager: ConnectionManager, line: str) -> str | None:
    parts = shlex.split(line)
    if len(parts) < 3:
        print("Usage: /prompt <server> <name> [key=value ...]")
        return None
    server, name = parts[1], parts[2]
    kwargs = dict(p.split("=", 1) for p in parts[3:] if "=" in p)
    try:
        return await manager.get_prompt(server, name, kwargs)
    except Exception as e:
        print(f"Could not load prompt: {e}")
        return None


async def amain(args: argparse.Namespace) -> int:
    cfg = load_config()
    specs = load_registry(cfg.registry_path)
    logger = CallLogger(cfg.log_dir)
    permissions = Permissions.from_specs(specs)

    def on_state(name: str, state: str, error: str | None) -> None:
        logger.event("server_state", server=name, state=state, error=error)
        if state in ("up", "down"):
            print(f"\n[server {name}: {state}{' - ' + error if error and state == 'down' else ''}]", file=sys.stderr)

    async with ConnectionManager(specs, cfg, on_state) as manager:
        router = ToolRouter(manager, permissions, cfg)
        llm = LLMClient(cfg.model, cfg.max_tokens)
        agent = AgentLoop(
            cfg=cfg,
            llm=llm,
            router=router,
            planner=Planner(llm),
            selector=ToolSelector(cfg.max_tools_in_context),
            gate=ApprovalGate(auto_approve=args.auto_approve),
            policy=DegradationPolicy(router, manager, cfg.reconnect_wait_s),
            logger=logger,
            context=await collect_schema_context(manager),
        )

        if args.task:
            await run_task(agent, " ".join(args.task))
        else:
            print_status(manager, router)
            while True:
                try:
                    line = (await asyncio.to_thread(input, "\n> ")).strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not line:
                    continue
                if line in ("/quit", "/exit"):
                    break
                if line == "/tools":
                    for t in router.tools():
                        kind = "read-only" if t.read_only else ("DESTRUCTIVE" if t.destructive else "write")
                        print(f"  {t.namespaced:38} {kind}")
                    continue
                if line == "/servers":
                    print_status(manager, router)
                    continue
                if line == "/prompts":
                    for name, c in manager.connections.items():
                        for p in (c.capabilities.prompts if c.capabilities else []):
                            print(f"  {name} {p.name} ({', '.join(p.arguments)})  {p.description}")
                    continue
                if line.startswith("/prompt "):
                    task = await expand_prompt(manager, line)
                    if task is None:
                        continue
                    print(f"\n(prompt expanded)\n{task}")
                else:
                    task = line
                await run_task(agent, task)

    print(f"\nTrace: {logger.path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP ecosystem agent")
    parser.add_argument("task", nargs="*", help="optional one-shot request")
    parser.add_argument("--auto-approve", action="store_true", help="skip approval prompts (demo only)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return asyncio.run(amain(args))
    except (RegistryError, MissingSecretError) as e:
        print(f"Startup error: {e}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())