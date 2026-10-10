"""Local .ics file backend. No OAuth needed. (Recurring events are not expanded.)"""
import uuid
from datetime import date, datetime
from pathlib import Path

from icalendar import Calendar
from icalendar import Event as IcsEvent

from .. import config
from . import Event


def _as_datetime(value) -> datetime:
    dt = value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=config.TZ)
    return dt.astimezone(config.TZ)


def _as_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


class IcsProvider:
    def __init__(self, path: Path):
        self.path = path

    def _load(self) -> Calendar:
        if self.path.exists():
            return Calendar.from_ical(self.path.read_bytes())
        cal = Calendar()
        cal.add("prodid", "-//mcp-ecosystem//EN")
        cal.add("version", "2.0")
        return cal

    def list_events(self, start: datetime, end: datetime) -> list[Event]:
        events: list[Event] = []
        for comp in self._load().walk("VEVENT"):
            s = _as_datetime(comp.decoded("DTSTART"))
            e = _as_datetime(comp.decoded("DTEND")) if comp.get("DTEND") else s
            if e > start and s < end:
                attendees = [str(a).replace("mailto:", "") for a in _as_list(comp.get("ATTENDEE"))]
                events.append(
                    Event(
                        id=str(comp.get("UID", "")),
                        title=str(comp.get("SUMMARY", "(no title)")),
                        start=s,
                        end=e,
                        attendees=attendees,
                        description=str(comp.get("DESCRIPTION", "")),
                    )
                )
        return sorted(events, key=lambda ev: ev.start)

    def create_event(self, title, start, end, attendees, description) -> Event:
        cal = self._load()
        uid = f"{uuid.uuid4()}@mcp-ecosystem"
        ev = IcsEvent()
        ev.add("uid", uid)
        ev.add("summary", title)
        ev.add("dtstart", start)
        ev.add("dtend", end)
        ev.add("dtstamp", datetime.now(config.TZ))
        if description:
            ev.add("description", description)
        for a in attendees:
            ev.add("attendee", f"mailto:{a}")
        cal.add_component(ev)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(cal.to_ical())
        return Event(uid, title, start, end, list(attendees), description)