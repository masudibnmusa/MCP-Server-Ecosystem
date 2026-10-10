"""Google Calendar backend. Switch on with CALENDAR_PROVIDER=google."""
from datetime import date, datetime, time

from .. import config
from ..auth import get_credentials
from . import Event


def _parse(d: dict) -> datetime:
    if "dateTime" in d:
        return datetime.fromisoformat(d["dateTime"].replace("Z", "+00:00")).astimezone(config.TZ)
    return datetime.combine(date.fromisoformat(d["date"]), time.min, tzinfo=config.TZ)


class GoogleProvider:
    def __init__(self, calendar_id: str = "primary"):
        from googleapiclient.discovery import build

        self.calendar_id = calendar_id
        self.service = build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)

    def list_events(self, start: datetime, end: datetime) -> list[Event]:
        resp = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=250,
            )
            .execute()
        )
        return [
            Event(
                id=item["id"],
                title=item.get("summary", "(no title)"),
                start=_parse(item["start"]),
                end=_parse(item["end"]),
                attendees=[a["email"] for a in item.get("attendees", [])],
                description=item.get("description", ""),
            )
            for item in resp.get("items", [])
        ]

    def create_event(self, title, start, end, attendees, description) -> Event:
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
            "attendees": [{"email": a} for a in attendees],
        }
        item = self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
        return Event(item["id"], title, start, end, list(attendees), description)