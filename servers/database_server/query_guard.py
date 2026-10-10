"""AST-based validation of model-written SQL (sqlglot).

Defense in depth: this is layer 2. Layer 1 is the read-only connection in connection.py.
We execute the NORMALIZED sql returned here, never the raw string, so comments and
formatting tricks can't smuggle anything past the check.
"""
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from servers.shared.errors import ToolInputError

_SetOp = getattr(exp, "SetOperation", exp.Union)  # name differs across sqlglot versions
_ALLOWED_ROOTS = (exp.Select, exp.Union, _SetOp, exp.Subquery)

_BLOCKED_NODES = {
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "AlterTable", "Merge",
    "TruncateTable", "Command", "Pragma", "Attach", "Detach", "Transaction",
    "Commit", "Rollback", "Set", "Use",
}
_BLOCKED_FUNCTIONS = {"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"}


def validate_select(sql: str) -> str:
    """Return normalized, validated SQL or raise ToolInputError."""
    if not sql or not sql.strip():
        raise ToolInputError("The query is empty.", hint="Pass a single SELECT statement.")

    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except ParseError as e:
        raise ToolInputError(
            f"The SQL could not be parsed: {str(e)[:200]}",
            hint="Use valid SQLite syntax and a single SELECT statement.",
        )

    if len(statements) != 1:
        raise ToolInputError(
            "Exactly one statement is allowed.", hint="Remove extra statements after the semicolon."
        )

    tree = statements[0]
    if not isinstance(tree, _ALLOWED_ROOTS):
        raise ToolInputError(
            f"Only read-only SELECT queries are allowed (got {type(tree).__name__}).",
            hint="This tool cannot modify data.",
        )

    for node in tree.find_all(exp.Expression):
        name = type(node).__name__
        if name in _BLOCKED_NODES:
            raise ToolInputError(f"{name} operations are not allowed in read-only queries.")
        if isinstance(node, exp.Anonymous) and str(node.name).lower() in _BLOCKED_FUNCTIONS:
            raise ToolInputError(f"The function {node.name}() is not allowed.")

    return tree.sql(dialect="sqlite")