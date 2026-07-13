"""SQLite adapter — async via aiosqlite. Read-only, timeout, row-limited."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from uuid import uuid4

import aiosqlite

from app.config import settings
from app.db.base import (
    ColumnInfo,
    DBAdapter,
    ForeignKey,
    QueryResult,
    TableInfo,
)
from app.db.safety import assert_read_only


class SQLiteAdapter:
    """Adapter for a local SQLite file. Opens the file in read-only URI mode."""

    def __init__(self, db_path: str | Path, connection_id: str | None = None):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"SQLite file not found: {self.db_path}")
        self.connection_id = connection_id or f"sqlite:{uuid4().hex[:8]}"
        # file:...?mode=ro forces read-only at the driver level — layered defense.
        self._uri = f"file:{self.db_path.resolve()}?mode=ro"

    async def list_tables(self) -> list[TableInfo]:
        async with aiosqlite.connect(self._uri, uri=True) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            table_names = [row["name"] for row in await cur.fetchall()]

            tables: list[TableInfo] = []
            for name in table_names:
                cols_cur = await conn.execute(f"PRAGMA table_info({_quote(name)})")
                cols_rows = await cols_cur.fetchall()
                cols = [
                    ColumnInfo(
                        name=r["name"],
                        type=(r["type"] or "").upper() or "ANY",
                        nullable=(r["notnull"] == 0),
                        primary_key=(r["pk"] > 0),
                        default=str(r["dflt_value"]) if r["dflt_value"] is not None else None,
                    )
                    for r in cols_rows
                ]
                tables.append(TableInfo(name=name, columns=cols))
            return tables

    async def get_sample_rows(self, table: str, limit: int = 3) -> QueryResult:
        limit = min(limit, settings.max_result_rows)
        sql = f"SELECT * FROM {_quote(table)} LIMIT {int(limit)}"
        return await self.execute_read(sql)

    async def get_foreign_keys(self) -> list[ForeignKey]:
        fks: list[ForeignKey] = []
        async with aiosqlite.connect(self._uri, uri=True) as conn:
            conn.row_factory = aiosqlite.Row
            names_cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            table_names = [row["name"] for row in await names_cur.fetchall()]
            for name in table_names:
                fk_cur = await conn.execute(f"PRAGMA foreign_key_list({_quote(name)})")
                for row in await fk_cur.fetchall():
                    fks.append(
                        ForeignKey(
                            from_table=name,
                            from_column=row["from"],
                            to_table=row["table"],
                            to_column=row["to"],
                        )
                    )
        return fks

    async def execute_read(self, sql: str) -> QueryResult:
        safe_sql = assert_read_only(sql, dialect="sqlite")
        start = time.perf_counter()
        try:
            async with asyncio.timeout(settings.query_timeout_seconds):
                async with aiosqlite.connect(self._uri, uri=True) as conn:
                    cur = await conn.execute(safe_sql)
                    columns = [d[0] for d in cur.description] if cur.description else []
                    fetched = await cur.fetchmany(settings.max_result_rows + 1)
                    truncated = len(fetched) > settings.max_result_rows
                    rows = [tuple(r) for r in fetched[: settings.max_result_rows]]
        except TimeoutError as e:
            raise TimeoutError(
                f"Query exceeded {settings.query_timeout_seconds}s timeout"
            ) from e

        elapsed_ms = (time.perf_counter() - start) * 1000
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=elapsed_ms,
        )

    async def close(self) -> None:
        # Nothing persistent to close — connections are per-call.
        return None


def _quote(ident: str) -> str:
    """Double-quote an identifier for SQLite, escaping any embedded quotes."""
    return '"' + ident.replace('"', '""') + '"'


# Type-check: ensure adapter satisfies protocol.
_: DBAdapter = SQLiteAdapter.__new__(SQLiteAdapter)  # type: ignore[assignment]
