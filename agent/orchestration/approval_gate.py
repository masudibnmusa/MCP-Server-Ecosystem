"""The single place where approval is ENFORCED. Servers only DECLARE annotations.

A tool runs without approval only if: its server is marked trusted in the registry AND it
declares readOnlyHint=True. Everything else (writes, destructive, unknown, untrusted) asks.
"""
import asyncio
import json

from agent.mcp_client.capability_loader import ToolInfo

APPROVED = "approved"
APPROVED_ALWAYS = "approved_always"
DENIED = "denied"


class ApprovalGate:
    def __init__(self, auto_approve: bool = False):
        self.auto_approve = auto_approve  # demo/testing only
        self._always: set[str] = set()

    def needs_approval(self, tool: ToolInfo) -> bool:
        return not (tool.read_only and tool.trusted)

    async def request(self, tool: ToolInfo, arguments: dict) -> str:
        if tool.namespaced in self._always:
            return APPROVED_ALWAYS
        if self.auto_approve:
            print(f"  [auto-approved] {tool.namespaced}")
            return APPROVED
        decision = await asyncio.to_thread(self._ask, tool, arguments)
        if decision == APPROVED_ALWAYS:
            self._always.add(tool.namespaced)
        return decision

    def _ask(self, tool: ToolInfo, arguments: dict) -> str:
        effect = "MAY MODIFY OR DELETE DATA" if tool.destructive else "writes data"
        if not tool.trusted:
            effect += " (server not trusted)"
        args = json.dumps(arguments, indent=2, default=str)
        args = "\n".join("│   " + line[:500] for line in args.splitlines())

        print("\n┌─ Approval needed ─────────────────────────────")
        print(f"│ tool:   {tool.namespaced}")
        print(f"│ effect: {effect}")
        print("│ args:")
        print(args)
        options = "[y]es / [n]o" if tool.destructive else "[y]es / [n]o / [a]lways this session"
        try:
            answer = input(f"└─ Approve? {options}: ").strip().lower()
        except EOFError:
            return DENIED
        if answer in ("y", "yes"):
            return APPROVED
        if answer in ("a", "always") and not tool.destructive:
            return APPROVED_ALWAYS
        return DENIED