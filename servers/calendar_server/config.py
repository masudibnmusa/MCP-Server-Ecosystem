import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]

PROVIDER = os.getenv("CALENDAR_PROVIDER", "ics").lower()  # "ics" or "google"

ICS_PATH = Path(os.getenv("ICS_PATH", "data/sample_calendar.ics"))
if not ICS_PATH.is_absolute():
    ICS_PATH = ROOT / ICS_PATH

TZ = ZoneInfo(os.getenv("CALENDAR_TZ", "UTC"))
WORK_START = time.fromisoformat(os.getenv("WORK_START", "09:00"))
WORK_END = time.fromisoformat(os.getenv("WORK_END", "17:00"))
WORK_DAYS = (0, 1, 2, 3, 4)  # Monday to Friday