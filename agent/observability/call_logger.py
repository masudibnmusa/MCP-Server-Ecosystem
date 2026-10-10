"""One JSON line per event. Every tool call records server, args, result, latency, approval."""
import json
from datetime import datetime
from pathlib import Path

from security.secrets_manager import redact

MAX_RESULT_CHARS = 2000


class CallLogger:
    def __init__(self, log_dir: Path, session_id: str | None = None):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.path = log_dir / f"{self.session_id}.jsonl"

    def _write(self, record: dict) -> None:
        record = {"ts": datetime.now().isoformat(timespec="seconds"), **record}
        line = redact(json.dumps(record, default=str))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def record_call(
        self,
        *,
        server: str,
        tool: str,
        arguments: dict,
        result: str,
        is_error: bool,
        latency_ms: int,
        approval: str,
        flagged: list[str] | None = None,
    ) -> None:
        self._write(
            {
                "kind": "tool_call",
                "server": server,
                "tool": tool,
                "arguments": arguments,
                "result": result[:MAX_RESULT_CHARS],
                "is_error": is_error,
                "latency_ms": latency_ms,
                "approval": approval,
                "injection_flags": flagged,
            }
        )

    def event(self, kind: str, **fields) -> None:
        self._write({"kind": kind, **fields})