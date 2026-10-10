import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]

DB_PATH = Path(os.getenv("DB_PATH", "data/sample_db/demo.sqlite"))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH

MAX_ROWS = int(os.getenv("DB_MAX_ROWS", "200"))
QUERY_TIMEOUT_S = float(os.getenv("DB_QUERY_TIMEOUT_S", "5"))