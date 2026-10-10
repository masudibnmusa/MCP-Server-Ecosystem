"""Calendar backends are swappable: tools.py only talks to this interface."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class Event:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "attendees": self.attendees,
            "description": self.description,
        }


class CalendarProvider(Protocol):
    def list_events(self, start: datetime, end: datetime) -> list[Event]: ...

    def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str],
        description: str,
    ) -> Event: ...


def get_provider() -> CalendarProvider:
    from .. import config

    if config.PROVIDER == "google":
        from .google_provider import GoogleProvider

        return GoogleProvider()
    from .ics_provider import IcsProvider

    return IcsProvider(config.ICS_PATH)