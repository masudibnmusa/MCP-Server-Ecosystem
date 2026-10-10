"""Keep the model's context small. With few tools, pass them all. With many, rank by keyword
overlap with the task. (Swap in embedding search later if the tool count grows a lot.)"""
import re

from agent.mcp_client.capability_loader import ToolInfo

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(text.lower()):
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return out


class ToolSelector:
    def __init__(self, max_tools: int = 20):
        self.max_tools = max_tools

    def select(self, task: str, tools: list[ToolInfo]) -> list[ToolInfo]:
        if len(tools) <= self.max_tools:
            return tools
        query = _tokens(task)

        def score(t: ToolInfo) -> int:
            return len(query & _tokens(f"{t.server} {t.name} {t.description}"))

        ranked = sorted(tools, key=lambda t: (-score(t), not t.read_only, t.namespaced))
        return ranked[: self.max_tools]