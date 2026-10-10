"""Per-server, per-tool allow/deny rules from the registry. Deny always wins.

- If a server has an `allow` list, only matching tools are permitted.
- Patterns support wildcards: "list_*", "*".
- Unknown servers are denied (fail closed).
"""
import fnmatch

from registry.registry_loader import ServerSpec


class Permissions:
    def __init__(self, rules: dict[str, tuple[tuple[str, ...], tuple[str, ...]]]):
        self._rules = rules  # server -> (allow, deny)

    @classmethod
    def from_specs(cls, specs: list[ServerSpec]) -> "Permissions":
        return cls({s.name: (s.allow, s.deny) for s in specs})

    def is_allowed(self, server: str, tool: str) -> bool:
        if server not in self._rules:
            return False
        allow, deny = self._rules[server]
        if any(fnmatch.fnmatchcase(tool, p) for p in deny):
            return False
        if allow:
            return any(fnmatch.fnmatchcase(tool, p) for p in allow)
        return True