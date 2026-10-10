"""Create the demo SQLite database and sample calendar.

Run from the repo root:  python -m data.seed
"""
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar, Event

ROOT = Path(__file__).resolve().parent
DB = ROOT / "sample_db" / "demo.sqlite"
ICS = ROOT / "sample_calendar.ics"

CUSTOMERS = [
    ("Acme Corp", "Enterprise", "US"),
    ("Globex", "Enterprise", "DE"),
    ("Initech", "Mid-market", "US"),
    ("Umbrella Ltd", "Enterprise", "UK"),
    ("Hooli", "Mid-market", "US"),
    ("Stark Industries", "Enterprise", "US"),
    ("Wayne Enterprises", "Enterprise", "US"),
    ("Wonka Foods", "SMB", "CH"),
    ("Soylent", "SMB", "US"),
    ("Cyberdyne", "Mid-market", "JP"),
]
SCALE = {"Enterprise": 50_000, "Mid-market": 15_000, "SMB": 3_000}


def seed_db() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(
        """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            segment TEXT,
            country TEXT,
            contact_email TEXT
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            amount REAL NOT NULL,
            ordered_at TEXT NOT NULL
        );
        """
    )
    rnd = random.Random(42)
    now = datetime.now(timezone.utc)
    for name, segment, country in CUSTOMERS:
        slug = name.lower().replace(" ", "")
        cur = con.execute(
            "INSERT INTO customers (name, segment, country, contact_email) VALUES (?,?,?,?)",
            (name, segment, country, f"contact@{slug}.example"),
        )
        for _ in range(rnd.randint(3, 8)):
            amount = round(rnd.uniform(0.2, 1.0) * SCALE[segment], 2)
            when = (now - timedelta(days=rnd.randint(1, 365))).date().isoformat()
            con.execute(
                "INSERT INTO orders (customer_id, amount, ordered_at) VALUES (?,?,?)",
                (cur.lastrowid, amount, when),
            )
    con.commit()
    con.close()
    print(f"Created {DB}")


def seed_calendar() -> None:
    cal = Calendar()
    cal.add("prodid", "-//mcp-ecosystem demo//EN")
    cal.add("version", "2.0")
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    def add(day, h1, m1, h2, m2, title):
        ev = Event()
        ev.add("uid", f"{title}-{day.date()}@demo".replace(" ", "-"))
        ev.add("summary", title)
        ev.add("dtstart", day.replace(hour=h1, minute=m1))
        ev.add("dtend", day.replace(hour=h2, minute=m2))
        ev.add("dtstamp", today)
        cal.add_component(ev)

    for offset in range(14):
        day = today + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        add(day, 9, 30, 10, 0, "Team standup")
        if day.weekday() in (1, 3):
            add(day, 13, 0, 14, 30, "Planning")
        if day.weekday() == 2:
            add(day, 11, 0, 12, 0, "1:1 with manager")

    ICS.write_bytes(cal.to_ical())
    print(f"Created {ICS}")


if __name__ == "__main__":
    seed_db()
    seed_calendar()