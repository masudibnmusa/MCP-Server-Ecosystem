from datetime import datetime, timedelta
from functools import lru_cache

from mcp.server.fastmcp import FastMCP

from servers.shared.annotations import READ_ONLY, WRITE_ADDITIVE
from servers.shared.errors import ToolInputError

from . import config
from .providers import get_provider

MAX_RANGE_DAYS = 31


@lru_cache(maxsize=1)
def _provider():
    return get_provider()


def _parse(value: str, name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ToolInputError(
            f"'{name}' must be an ISO-8601 date or datetime, got {value!r}.",
            hint="Example: 2026-10-12T14:00:00",
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.TZ)
    return dt.astimezone(config.TZ)


def _check_range(start: datetime, end: datetime) -> None:
    if end <= start:
        raise ToolInputError("'end' must be after 'start'.")
    if end - start > timedelta(days=MAX_RANGE_DAYS):
        raise ToolInputError(f"Range is too large. Maximum is {MAX_RANGE_DAYS} days.")


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def list_events(start: str, end: str) -> list[dict]:
        """List calendar events between two ISO-8601 datetimes (max 31 days)."""
        s, e = _parse(start, "start"), _parse(end, "end")
        _check_range(s, e)
        return [ev.to_dict() for ev in _provider().list_events(s, e)]

    @mcp.tool(annotations=READ_ONLY)
    def find_free_slots(start: str, end: str, duration_minutes: int = 30, limit: int = 5) -> dict:
        """Find open slots of a given length inside working hours (Mon-Fri) between two ISO-8601
        datetimes. Returns at most `limit` slots, earliest first. Use this BEFORE create_event."""
        s, e = _parse(start, "start"), _parse(end, "end")
        _check_range(s, e)
        if not 5 <= duration_minutes <= 480:
            raise ToolInputError("duration_minutes must be between 5 and 480.")
        limit = max(1, min(limit, 20))
        delta = timedelta(minutes=duration_minutes)
        busy = sorted((ev.start, ev.end) for ev in _provider().list_events(s, e))

        slots: list[dict] = []

        def add(slot_start: datetime) -> None:
            slots.append(
                {"start": slot_start.isoformat(), "end": (slot_start + delta).isoformat()}
            )

        day = s.date()
        while day <= e.date() and len(slots) < limit:
            if day.weekday() in config.WORK_DAYS:
                win_start = max(datetime.combine(day, config.WORK_START, tzinfo=config.TZ), s)
                win_end = min(datetime.combine(day, config.WORK_END, tzinfo=config.TZ), e)
                cursor = win_start
                for b_start, b_end in busy:
                    if b_end <= cursor or b_start >= win_end:
                        continue
                    if b_start - cursor >= delta and len(slots) < limit:
                        add(cursor)
                    cursor = max(cursor, b_end)
                if win_end - cursor >= delta and len(slots) < limit:
                    add(cursor)
            day += timedelta(days=1)

        return {"timezone": str(config.TZ), "duration_minutes": duration_minutes, "slots": slots}

    @mcp.tool(annotations=WRITE_ADDITIVE)
    def create_event(
        title: str,
        start: str,
        end: str,
        attendees: list[str] | None = None,
        description: str = "",
    ) -> dict:
        """Create a calendar event. Requires user approval. Call find_free_slots first so the
        event does not collide with existing ones."""
        if not title.strip():
            raise ToolInputError("'title' must not be empty.")
        s, e = _parse(start, "start"), _parse(end, "end")
        _check_range(s, e)

        conflicts = _provider().list_events(s, e)
        if conflicts:
            names = ", ".join(f"{c.title} ({c.start:%H:%M}-{c.end:%H:%M})" for c in conflicts)
            raise ToolInputError(
                f"That time overlaps existing events: {names}.",
                hint="Call find_free_slots to choose a free time.",
            )
        ev = _provider().create_event(title.strip(), s, e, attendees or [], description)
        return ev.to_dict()