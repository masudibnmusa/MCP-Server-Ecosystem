"""The LLM tool-use loop across all servers, driven by the planner.

For each plan step:  LLM chooses tools -> permission/approval check -> route to server
-> wrap result as untrusted -> log -> back to the LLM.
A step that reports failure triggers a re-plan (up to cfg.max_replans).
"""
import json
import re
import time

from agent.config import AgentConfig
from agent.llm.llm_client import LLMClient
from agent.llm.prompts import build_system_prompt, step_instruction
from agent.mcp_client.tool_router import ToolRouter
from agent.observability.call_logger import CallLogger
from security.injection_guard import guard_result

from .approval_gate import DENIED, ApprovalGate
from .degradation import DegradationPolicy
from .planner import Plan, Planner
from .tool_selector import ToolSelector

_PREFIX_RE = re.compile(r"^\s*STEP (?:DONE|FAILED)\s*:?\s*", re.IGNORECASE)


def _failed(text: str) -> bool:
    return text.strip().upper().startswith("STEP FAILED")


def _strip_prefix(text: str) -> str:
    return _PREFIX_RE.sub("", text, count=1).strip()


def _tool_result(tool_use_id: str, content: str, is_error: bool) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error}


class AgentLoop:
    def __init__(
        self,
        *,
        cfg: AgentConfig,
        llm: LLMClient,
        router: ToolRouter,
        planner: Planner,
        selector: ToolSelector,
        gate: ApprovalGate,
        policy: DegradationPolicy,
        logger: CallLogger,
        context: str = "",
    ):
        self.cfg, self.llm, self.router, self.planner = cfg, llm, router, planner
        self.selector, self.gate, self.policy, self.logger = selector, gate, policy, logger
        self.context = context
        self.messages: list[dict] = []  # conversation history across turns

    async def run(self, task: str) -> str:
        checkpoint = len(self.messages)
        try:
            return await self._run(task)
        except BaseException:
            del self.messages[checkpoint:]  # never leave a dangling tool_use in the history
            raise

    async def _run(self, task: str) -> str:
        system = build_system_prompt(self.policy.unavailable_servers(), self.context)
        tools = self.selector.select(task, self.router.tools())
        if not tools:
            return "No tools are available right now (servers are down or access is denied)."
        tool_defs = [t.to_llm() for t in tools]

        plan = await self.planner.draft(task, tools)
        self._show_plan("Plan", plan)
        self.logger.event("plan", steps=[s.description for s in plan.steps])

        final: str | None = None
        replans = 0
        first = True
        while (step := plan.next_pending()) is not None:
            is_last = plan.is_last(step)
            print(f"\n[step {step.id}] {step.description}")
            text = await self._tool_loop(
                system, tool_defs, step_instruction(task, plan.as_text(), step, is_last, first)
            )
            first = False

            if _failed(text):
                step.status, step.result = "failed", _strip_prefix(text)
                self.logger.event("step_failed", step=step.id, reason=step.result)
                if replans >= self.cfg.max_replans:
                    return self._give_up(plan, step.result)
                replans += 1
                plan = await self.planner.replan(task, plan, step, tools)
                self._show_plan("Revised plan", plan)
                self.logger.event("replan", steps=[s.description for s in plan.steps])
                continue

            step.status, step.result = "done", _strip_prefix(text)
            if is_last:
                final = text

        if final is None:
            final = await self._tool_loop(
                system,
                tool_defs,
                "All steps are finished. Write the final answer for the user. "
                "Do not call more tools unless essential.",
            )
        return final

    async def _tool_loop(self, system: str, tool_defs: list[dict], user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(self.cfg.max_tool_rounds):
            resp = await self.llm.complete(system, self.messages, tool_defs)
            self.messages.append({"role": "assistant", "content": resp.content})

            uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not uses:
                return "".join(b.text for b in resp.content if b.type == "text").strip()

            results = [await self._run_tool_call(b) for b in uses]  # sequential: keeps approvals ordered
            self.messages.append({"role": "user", "content": results})
        return "STEP FAILED: too many tool rounds without finishing."

    async def _run_tool_call(self, block) -> dict:
        args = block.input if isinstance(block.input, dict) else {}
        info = self.router.resolve(block.name)
        if info is None:
            msg = f"Unknown or not-permitted tool '{block.name}'. Use only the tools you were given."
            return _tool_result(block.id, msg, True)

        print(f"  → {info.namespaced} {json.dumps(args, default=str)[:120]}")

        approval = "auto"
        if self.gate.needs_approval(info):
            approval = await self.gate.request(info, args)
            if approval == DENIED:
                self.logger.record_call(
                    server=info.server, tool=info.name, arguments=args,
                    result="(denied by user)", is_error=True, latency_ms=0, approval=DENIED,
                )
                return _tool_result(
                    block.id,
                    "The user denied this action. Do not retry it. Continue with other work or ask "
                    "the user what they would prefer.",
                    True,
                )

        start = time.perf_counter()
        result = await self.policy.call(info, args)
        latency_ms = int((time.perf_counter() - start) * 1000)

        guarded = guard_result(info.server, info.name, result.text, self.cfg.max_result_chars)
        if guarded.flagged:
            print(f"  ⚠ result from {info.namespaced} looks like it contains instructions (treated as data)")
        print(f"    {'✗' if result.is_error else '✓'} {latency_ms} ms")

        self.logger.record_call(
            server=info.server, tool=info.name, arguments=args, result=result.text,
            is_error=result.is_error, latency_ms=latency_ms, approval=approval,
            flagged=guarded.flagged or None,
        )
        return _tool_result(block.id, guarded.text, result.is_error)

    @staticmethod
    def _show_plan(label: str, plan: Plan) -> None:
        print(f"\n{label}:")
        for s in plan.steps:
            mark = "✓" if s.status == "done" else " "
            print(f"  {mark} {s.id}. {s.description}")

    @staticmethod
    def _give_up(plan: Plan, reason: str) -> str:
        done = [s for s in plan.steps if s.status == "done"]
        done_text = "\n".join(f"- {s.description}: {s.result}" for s in done) or "- (nothing completed)"
        return f"I wasn't able to finish everything.\n\nCompleted:\n{done_text}\n\nProblem: {reason}"