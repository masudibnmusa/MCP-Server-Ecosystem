"""Common input/output models shared across servers."""
from pydantic import BaseModel, Field


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool = False


class TimeSlot(BaseModel):
    start: str = Field(description="ISO-8601 start time")
    end: str = Field(description="ISO-8601 end time")


class CalendarEvent(BaseModel):
    id: str
    title: str
    start: str
    end: str
    attendees: list[str] = []
    description: str = ""


class Ticket(BaseModel):
    id: str
    title: str
    description: str = ""
    priority: str = "medium"
    assignee: str | None = None
    created_at: str