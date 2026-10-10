"""List tools, resources, and prompts from one connected server.

Note: pagination cursors are not followed. FastMCP servers return everything in one page.
"""
import logging
from dataclasses import dataclass, field

from mcp.shared.exceptions import McpError

from registry.registry_loader import ServerSpec

from .namespace import NamespaceError, make_name

log = logging.getLogger("mcp.capabilities")


@dataclass(frozen=True)
class ToolInfo:
    server: str
    name: str  # original name on the server
    namespaced: str  # what the LLM sees
    description: str
    input_schema: dict
    read_only: bool
    destructive: bool
    idempotent: bool
    trusted: bool  # server is trusted, so its annotations are honored

    def to_llm(self) -> dict:
        return {
            "name": self.namespaced,
            "description": self.description or self.name,
            "input_schema": self.input_schema,
        }


@dataclass(frozen=True)
class PromptInfo:
    server: str
    name: str
    description: str
    arguments: tuple[str, ...]


@dataclass
class Capabilities:
    tools: list[ToolInfo] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    resource_templates: list[dict] = field(default_factory=list)
    prompts: list[PromptInfo] = field(default_factory=list)

    def tool(self, name: str) -> ToolInfo | None:
        return next((t for t in self.tools if t.name == name), None)


async def _list(fn, attr: str) -> list:
    try:
        return list(getattr(await fn(), attr))
    except McpError:
        return []  # server does not support this capability


async def load_capabilities(spec: ServerSpec, session) -> Capabilities:
    caps = Capabilities()
    seen: set[str] = set()

    for t in (await session.list_tools()).tools:
        try:
            ns = make_name(spec.name, t.name)
        except NamespaceError as e:
            log.warning("Skipping tool from %s: %s", spec.name, e)
            continue
        if ns in seen:
            log.warning("Duplicate tool %s from %s ignored", ns, spec.name)
            continue
        seen.add(ns)

        ann = t.annotations
        read_only = bool(ann and ann.readOnlyHint is True)
        # MCP default: a non-read-only tool is destructive unless it says otherwise.
        destructive = (not read_only) and not (ann and ann.destructiveHint is False)
        idempotent = bool(ann and ann.idempotentHint is True)

        caps.tools.append(
            ToolInfo(
                server=spec.name,
                name=t.name,
                namespaced=ns,
                description=(t.description or "").strip(),
                input_schema=t.inputSchema or {"type": "object", "properties": {}},
                read_only=read_only,
                destructive=destructive,
                idempotent=idempotent,
                trusted=spec.trusted,
            )
        )

    for r in await _list(session.list_resources, "resources"):
        caps.resources.append(
            {"uri": str(r.uri), "name": r.name, "description": getattr(r, "description", "") or ""}
        )
    for r in await _list(session.list_resource_templates, "resourceTemplates"):
        caps.resource_templates.append(
            {"uri_template": r.uriTemplate, "name": r.name, "description": getattr(r, "description", "") or ""}
        )
    for p in await _list(session.list_prompts, "prompts"):
        args = tuple(f"{a.name}{'*' if a.required else ''}" for a in (p.arguments or []))
        caps.prompts.append(PromptInfo(spec.name, p.name, p.description or "", args))

    return caps