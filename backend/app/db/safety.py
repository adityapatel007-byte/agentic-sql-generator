"""Read-only enforcement — reject any SQL that mutates state."""
from __future__ import annotations

import sqlglot
from sqlglot import exp


class UnsafeSQLError(ValueError):
    """Raised when the SQL contains write/DDL operations."""


# Only SELECT and WITH-then-SELECT are allowed. Nothing else.
_ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)

# Explicit deny-list of statement types — belt and braces.
_DENIED = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,  # CATCHES ATTACH, PRAGMA writes, VACUUM, COPY, etc. in sqlglot
)


def assert_read_only(sql: str, dialect: str = "sqlite") -> str:
    """Parse the SQL and raise UnsafeSQLError if anything mutates state.

    Returns the (possibly normalized) SQL when safe.
    """
    if not sql.strip():
        raise UnsafeSQLError("Empty SQL")

    try:
        parsed = sqlglot.parse(sql, read=dialect)
    except Exception as e:  # noqa: BLE001
        raise UnsafeSQLError(f"Could not parse SQL: {e}") from e

    if len(parsed) != 1 or parsed[0] is None:
        raise UnsafeSQLError("Exactly one statement is allowed")

    stmt = parsed[0]

    # Fast-path allow: top-level SELECT / WITH ... SELECT
    if isinstance(stmt, _ALLOWED_ROOTS):
        pass
    elif isinstance(stmt, exp.With):
        if not isinstance(stmt.this, _ALLOWED_ROOTS):
            raise UnsafeSQLError("WITH must wrap a SELECT")
    else:
        raise UnsafeSQLError(
            f"Only SELECT statements are allowed (got {stmt.__class__.__name__})"
        )

    # Walk the tree — any denied node anywhere = reject.
    for node in stmt.walk():
        if isinstance(node, _DENIED):
            raise UnsafeSQLError(
                f"Disallowed operation: {node.__class__.__name__}"
            )

    return stmt.sql(dialect=dialect)
