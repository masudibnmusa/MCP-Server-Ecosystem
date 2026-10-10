import sqlite3
from contextlib import closing

from mcp.server.fastmcp import FastMCP

from servers.shared.annotations import READ_ONLY
from servers.shared.errors import ToolExecutionError

from . import config
from .connection import quote_ident, read_only_connection, require_table, table_columns, table_names
from .query_guard import validate_select


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def list_tables() -> list[str]:
        """List every table and view in the database. Call this first to see what data exists."""
        with closing(read_only_connection()) as conn:
            return table_names(conn)

    @mcp.tool(annotations=READ_ONLY)
    def describe_table(table: str) -> dict:
        """Describe a table: column names, types, primary keys, and row count."""
        with closing(read_only_connection()) as conn:
            require_table(conn, table)
            count = conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0]
            return {"table": table, "columns": table_columns(conn, table), "row_count": count}

    @mcp.tool(annotations=READ_ONLY)
    def run_query(sql: str) -> dict:
        """Run ONE read-only SQLite SELECT query and return columns and rows.

        Only SELECT (including WITH/CTE and UNION) is allowed. Results are capped at a
        maximum number of rows (see `truncated` in the response), and queries have a time limit.
        Use list_tables and describe_table first to check names. Aggregate (SUM, COUNT, GROUP BY)
        instead of fetching raw rows when you can.
        """
        normalized = validate_select(sql)
        try:
            with closing(read_only_connection()) as conn:
                cur = conn.execute(normalized)
                rows = cur.fetchmany(config.MAX_ROWS + 1)
                columns = [d[0] for d in (cur.description or [])]
        except sqlite3.OperationalError as e:
            msg = str(e)
            if "interrupted" in msg:
                raise ToolExecutionError(
                    f"The query exceeded the {config.QUERY_TIMEOUT_S}s time limit.",
                    hint="Add filters, a LIMIT, or aggregate the data.",
                )
            raise ToolExecutionError(
                f"SQLite error: {msg}", hint="Use describe_table to check table and column names."
            )

        truncated = len(rows) > config.MAX_ROWS
        rows = rows[: config.MAX_ROWS]
        return {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }