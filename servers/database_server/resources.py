import json
from contextlib import closing

from mcp.server.fastmcp import FastMCP

from .connection import quote_ident, read_only_connection, require_table


def register(mcp: FastMCP) -> None:
    @mcp.resource("schema://main", mime_type="text/plain")
    def schema() -> str:
        """The full CREATE statements for every table and view."""
        with closing(read_only_connection()) as conn:
            rows = conn.execute(
                "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return ";\n\n".join(r[0] for r in rows) + ";"

    @mcp.resource("sample://{table}", mime_type="application/json")
    def sample(table: str) -> str:
        """Five sample rows from a table."""
        with closing(read_only_connection()) as conn:
            require_table(conn, table)
            cur = conn.execute(f"SELECT * FROM {quote_ident(table)} LIMIT 5")
            cols = [d[0] for d in cur.description]
            data = [dict(zip(cols, row)) for row in cur.fetchall()]
        return json.dumps(data, default=str, indent=2)