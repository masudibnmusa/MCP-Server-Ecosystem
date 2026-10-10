"""Demo internal tools. Tickets and chat are written to local JSONL files; swap in your real
ticketing / chat APIs inside these functions without changing the tool signatures."""
import json
import threading
from datetime import datetime, timezone
from typing import Literal

from mcp.server.fastmcp import FastMCP

from servers.shared.annotations import READ_ONLY, WRITE_ADDITIVE
from servers.shared.errors import ToolInputError

from . import config

_lock = threading.Lock()

_BUILTIN_WIKI = [
    {"title": "Customer review process",
     "text": "Account reviews happen quarterly. Prepare revenue trends, open tickets, and renewal dates."},
    {"title": "Escalation policy",
     "text": "High priority tickets are triaged within 4 hours. Page the on-call engineer for outages."},
    {"title": "Onboarding checklist",
     "text": "Create accounts, schedule a kickoff meeting, share the documentation, assign a buddy."},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _count_lines(path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as f:
        return sum(1 for _ in f)


def _wiki_pages() -> list[dict]:
    pages = []
    if config.WIKI_DIR.exists():
        for p in sorted(config.WIKI_DIR.glob("*.md")):
            pages.append({"title": p.stem.replace("_", " "), "text": p.read_text(encoding="utf-8")})
    return pages or _BUILTIN_WIKI


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=WRITE_ADDITIVE)
    def create_ticket(
        title: str,
        description: str = "",
        priority: Literal["low", "medium", "high"] = "medium",
        assignee: str | None = None,
    ) -> dict:
        """Create a ticket. Requires user approval. Returns the new ticket id."""
        if not title.strip():
            raise ToolInputError("'title' must not be empty.")
        with _lock:
            ticket = {
                "id": f"TCK-{_count_lines(config.TICKETS_FILE) + 1:04d}",
                "title": title.strip(),
                "description": description,
                "priority": priority,
                "assignee": assignee,
                "created_at": _now(),
            }
            _append(config.TICKETS_FILE, ticket)
        return ticket

    @mcp.tool(annotations=READ_ONLY)
    def search_wiki(query: str, limit: int = 3) -> list[dict]:
        """Search the internal wiki by keywords. Returns the best-matching pages with snippets."""
        words = [w for w in query.lower().split() if len(w) > 2]
        if not words:
            raise ToolInputError("Query is too short.", hint="Use at least one keyword of 3+ letters.")
        scored = []
        for page in _wiki_pages():
            haystack = f"{page['title']} {page['text']}".lower()
            score = sum(haystack.count(w) for w in words)
            if score:
                scored.append((score, page))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"title": p["title"], "snippet": p["text"][:300], "score": s}
            for s, p in scored[: max(1, min(limit, 10))]
        ]

    @mcp.tool(annotations=WRITE_ADDITIVE)
    def post_to_chat(channel: str, message: str) -> dict:
        """Post a message to a chat channel (e.g. '#sales'). Requires user approval.
        This demo queues the message to a local outbox file instead of calling a real chat API."""
        if not channel.startswith("#"):
            raise ToolInputError("Channel must start with '#'.", hint="Example: #sales")
        if not message.strip():
            raise ToolInputError("Message must not be empty.")
        if len(message) > config.MAX_MESSAGE_CHARS:
            raise ToolInputError(f"Message is longer than {config.MAX_MESSAGE_CHARS} characters.")
        with _lock:
            _append(config.CHAT_OUTBOX, {"channel": channel, "message": message, "at": _now()})
        return {"status": "queued", "channel": channel}