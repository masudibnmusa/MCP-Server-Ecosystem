"""Cross-server planning: draft a short step list, then (on failure) re-plan the remainder.

Planning is best-effort: if the model's JSON can't be parsed, we fall back to a single step
(the whole task) so the agent still works.
"""
import json
import logging
import re
from dataclasses import dataclass, field

from agent.llm.llm_client import LLMClient
from agent.llm.prompts import PLANNER_SYSTEM, planner_prompt, replan_prompt
from agent.mcp_client.capability_loader import ToolInfo

log = logging.getLogger("agent.planner")
MAX_STEPS = 6


@dataclass
class Step:
    id: int
    description: str
    tools: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | done | failed
    result: str = ""


@dataclass
class Plan:
    steps: list[Step]

    def pending(self) -> list[Step]:
        return [s for s in self.steps if s.status == "pending"]

    def next_pending(self) -> Step | None:
        p = self.pending()
        return p[0] if p else None

    def is_last(self, step: Step) -> bool:
        p = self.pending()
        return len(p) == 1 and p[0] is step

    def as_text(self) -> str:
        lines = []
        for s in self.steps:
            line = f"{s.id}. [{s.status}] {s.description}"
            if s.result:
                line += f"  -> {s.result[:200]}"
            lines.append(line)
        return "\n".join(lines)


def summarize_tools(tools: list[ToolInfo]) -> str:
    lines = []
    for t in tools:
        kind = "read-only" if t.read_only else "WRITE"
        first = t.description.splitlines()[0] if t.description else ""
        lines.append(f"- {t.namespaced} [{kind}]: {first[:140]}")
    return "\n".join(lines)


def _parse_steps(text: str, valid_tools: set[str]) -> list[tuple[str, list[str]]]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[tuple[str, list[str]]] = []
    for item in (data.get("steps") or [])[:MAX_STEPS]:
        if isinstance(item, str):
            desc, tools = item.strip(), []
        elif isinstance(item, dict):
            desc = str(item.get("description", "")).strip()
            tools = [t for t in item.get("tools", []) if t in valid_tools]
        else:
            continue
        if desc:
            out.append((desc, tools))
    return out


class Planner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def _ask(self, prompt: str, valid_tools: set[str]) -> list[tuple[str, list[str]]]:
        try:
            text = await self.llm.complete_text(PLANNER_SYSTEM, prompt)
            return _parse_steps(text, valid_tools)
        except Exception as e:
            log.warning("Planning call failed: %s", e)
            return []

    async def draft(self, task: str, tools: list[ToolInfo]) -> Plan:
        parsed = await self._ask(planner_prompt(task, summarize_tools(tools)), {t.namespaced for t in tools})
        if not parsed:
            parsed = [(task, [])]
        return Plan([Step(i + 1, d, t) for i, (d, t) in enumerate(parsed)])

    async def replan(self, task: str, plan: Plan, failed: Step, tools: list[ToolInfo]) -> Plan:
        done = [s for s in plan.steps if s.status == "done"]
        done_text = "\n".join(f"{s.id}. {s.description} -> {s.result[:200]}" for s in done) or "(none)"
        prompt = replan_prompt(task, done_text, failed.description, failed.result, summarize_tools(tools))
        parsed = await self._ask(prompt, {t.namespaced for t in tools})
        if not parsed:
            parsed = [
                (
                    "Finish as much of the user's task as possible with what is available, "
                    "then clearly explain what could not be done.",
                    [],
                )
            ]
        start = len(done)
        return Plan(done + [Step(start + i + 1, d, t) for i, (d, t) in enumerate(parsed)])