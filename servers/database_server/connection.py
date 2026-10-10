"""Two separate connections. Reads can never write, even if query_guard is bypassed."""
import sqlite3
import time

from servers.shared.errors import ToolExecutionError, ToolInputError

from . import config


def _ensure_db_exists() -> None:
    if not config.DB_PATH.exists():
        raise ToolExecutionError(
            f"Database file not found at {config.DB_PATH}.",
            hint="Run `python -m data.seed` to create the demo database.",
        )


def read_only_connection(timeout_s: float | None = None) -> sqlite3.Connection:
    """Opened with mode=ro, query_only=ON, and a hard deadline enforced by a progress handler."""
    _ensure_db_exists()
    timeout_s = config.QUERY_TIMEOUT_S if timeout_s is None else timeout_s
    conn = sqlite3.connect(
        f"file:{config.DB_PATH.as_posix()}?mode=ro", uri=True, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    return conn


def read_write_connection() -> sqlite3.Connection:
    """Used ONLY by write_tools.py."""
    _ensure_db_exists()
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_names(conn: sqlite3.Connection, include_views: bool = True) -> list[str]:
    kinds = "('table','view')" if include_views else "('table')"
    rows = conn.execute(
        f"SELECT name FROM sqlite_master WHERE type IN {kinds} "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [r[0] for r in rows]


def require_table(conn: sqlite3.Connection, table: str, include_views: bool = True) -> str:
    """Only real, existing table names ever reach a SQL string."""
    available = table_names(conn, include_views)
    if table not in available:
        raise ToolInputError(
            f"Table '{table}' does not exist.",
            hint=f"Available tables: {', '.join(available) or '(none)'}.",
        )
    return table


def table_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    return [
        {
            "name": r["name"],
            "type": r["type"],
            "not_null": bool(r["notnull"]),
            "primary_key": bool(r["pk"]),
        }
        for r in rows
    ]