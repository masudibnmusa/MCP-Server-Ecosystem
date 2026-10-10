import sqlite3
from contextlib import closing
from typing import Any

from mcp.server.fastmcp import FastMCP

from servers.shared.annotations import WRITE
from servers.shared.errors import ToolExecutionError, ToolInputError

from .connection import quote_ident, read_write_connection, require_table, table_columns

_SCALARS = (str, int, float, bool, type(None))


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=WRITE)
    def insert_record(table: str, record: dict[str, Any]) -> dict:
        """Insert ONE row into a table. `record` maps column names to values.

        This modifies the database and requires user approval. Check the columns with
        describe_table first. Tables only (not views).
        """
        if not record:
            raise ToolInputError("`record` is empty.", hint="Provide at least one column value.")
        bad = [k for k, v in record.items() if not isinstance(v, _SCALARS)]
        if bad:
            raise ToolInputError(f"Values for {bad} must be string, number, boolean, or null.")

        with closing(read_write_connection()) as conn:
            require_table(conn, table, include_views=False)
            valid = {c["name"] for c in table_columns(conn, table)}
            unknown = [k for k in record if k not in valid]
            if unknown:
                raise ToolInputError(
                    f"Unknown column(s): {unknown}.", hint=f"Valid columns: {sorted(valid)}."
                )

            cols = list(record)
            sql = (
                f"INSERT INTO {quote_ident(table)} "
                f"({', '.join(quote_ident(c) for c in cols)}) "
                f"VALUES ({', '.join('?' for _ in cols)})"
            )
            try:
                with conn:  # commits on success, rolls back on error
                    cur = conn.execute(sql, [record[c] for c in cols])
            except sqlite3.IntegrityError as e:
                raise ToolExecutionError(f"Constraint failed: {e}", hint="Check NOT NULL and foreign keys.")
            return {"table": table, "inserted_id": cur.lastrowid}