"""View a session trace.

    python -m agent.observability.trace_viewer data/logs/<session>.jsonl
    python -m agent.observability.trace_viewer            # latest trace
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from agent.config import load_config


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        path = Path(argv[0])
    else:
        files = sorted(load_config().log_dir.glob("*.jsonl"))
        if not files:
            print("No traces found.")
            return 1
        path = files[-1]
    if not path.exists():
        print(f"Trace not found: {path}")
        return 1

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Trace: {path}\n")
    print(f"{'TIME':8}  {'SERVER':12} {'TOOL':24} {'APPROVAL':16} {'MS':>6}  STATUS")
    print("-" * 80)

    per_server: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "ms": 0})
    for r in records:
        ts = r.get("ts", "")[11:19]
        if r.get("kind") == "tool_call":
            status = "ERROR" if r["is_error"] else "ok"
            if r.get("injection_flags"):
                status += " ⚠ injection-flag"
            print(
                f"{ts:8}  {r['server']:12} {r['tool']:24} {r['approval']:16} "
                f"{r['latency_ms']:>6}  {status}"
            )
            s = per_server[r["server"]]
            s["calls"] += 1
            s["errors"] += int(r["is_error"])
            s["ms"] += r["latency_ms"]
        else:
            extra = ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("ts", "kind"))
            print(f"{ts:8}  · {r.get('kind')}: {extra[:90]}")

    print("\nSummary")
    for name, s in per_server.items():
        avg = s["ms"] // max(s["calls"], 1)
        print(f"  {name:12} calls={s['calls']}  errors={s['errors']}  avg_latency={avg} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())