import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

TICKETS_FILE = DATA_DIR / "tickets.jsonl"
CHAT_OUTBOX = DATA_DIR / "chat_outbox.jsonl"
WIKI_DIR = DATA_DIR / "wiki"

MAX_MESSAGE_CHARS = int(os.getenv("MAX_CHAT_MESSAGE_CHARS", "2000"))