"""Postgres adapter — async via psycopg. Read-only, timeout, row-limited."""
from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import psycopg
from psycopg import sql as pgsql
from psycopg.rows import dict_row

from app.config import settings
from app.db.base import (
    ColumnInfo,
    DBAdapter,
    ForeignKey,
    QueryResult,
    TableInfo,
)
from app.db.safety import assert_read_only


class PostgresAdapter:
    """Adapter for a Postgres database, addressed by connection string.

    Every operation opens a short-lived read-only transaction. We do not
    hold a persistent connection so that this class is safe to hand across
    async tasks without worrying about connection ownership.
    """

    def __init__(
        self,
        conninfo: str,
        connection_id: str | None = None,
        include_schemas: tuple[str, ...] = ("public",),
    ):
        if not conninfo.strip():
            raise ValueError("Postgres conninfo must be non-empty")
        self.conninfo = conninfo
        self.connection_id = connection_id or f"postgres:{uuid4().hex[:8]}"
        self.include_schemas = tuple(include_schemas)

    async def _connect(self) -> psycopg.AsyncConnection:
        # autocommit=False + read-only txn is our defense-in-depth alongside safety.py.
        conn = await psycopg.AsyncConnection.connect(
            self.conninfo,
            autocommit=False,
            row_factory=dict_row,
        )
        await conn.set_read_only(True)
        return conn

    async def list_tables(self) -> list[TableInfo]:
        query = """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema = ANY(%s)
            ORDER BY table_schema, table_name
        """
        col_query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        pk_query = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema   = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = %s
              AND tc.table_name   = %s
        """

        tables: list[TableInfo] = []
        async with await self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (list(self.include_schemas),))
                pairs = [(r["table_schema"], r["table_name"]) for r in await cur.fetchall()]

                for schema, name in pairs:
                    await cur.execute(col_query, (schema, name))
                    col_rows = await cur.fetchall()

                    await cur.execute(pk_query, (schema, name))
                    pk_cols = {r["column_name"] for r in await cur.fetchall()}

                    cols = [
                        ColumnInfo(
                            name=r["column_name"],
                            type=(r["data_type"] or "").upper() or "ANY",
                            nullable=(r["is_nullable"] == "YES"),
                            primary_key=(r["column_name"] in pk_cols),
                            default=r["column_default"],
                        )
                        for r in col_rows
                    ]
                    tables.append(TableInfo(name=name, columns=cols, schema=schema))
        return tables

    async def get_sample_rows(self, table: str, limit: int = 3) -> QueryResult:
        limit = min(limit, settings.max_result_rows)
        schema, name = _split_qualified(table, default_schema=self.include_schemas[0])
        stmt = pgsql.SQL("SELECT * FROM {}.{} LIMIT {}").format(
            pgsql.Identifier(schema),
            pgsql.Identifier(name),
            pgsql.Literal(int(limit)),
        )
        rendered = stmt.as_string(None)  # produce a plain SQL string for the safety layer
        return await self.execute_read(rendered)

    async def get_foreign_keys(self) -> list[ForeignKey]:
        query = """
            SELECT
                tc.table_schema  AS from_schema,
                tc.table_name    AS from_table,
                kcu.column_name  AS from_column,
                ccu.table_schema AS to_schema,
                ccu.table_name   AS to_table,
                ccu.column_name  AS to_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema   = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema   = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = ANY(%s)
        """
        fks: list[ForeignKey] = []
        async with await self._connect() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (list(self.include_schemas),))
                for r in await cur.fetchall():
                    fks.append(
                        ForeignKey(
                            from_table=_qualify(r["from_schema"], r["from_table"]),
                            from_column=r["from_column"],
                            to_table=_qualify(r["to_schema"], r["to_table"]),
                            to_column=r["to_column"],
                        )
                    )
        return fks

    async def execute_read(self, sql: str) -> QueryResult:
        safe_sql = assert_read_only(sql, dialect="postgres")
        start = time.perf_counter()
        try:
            async with asyncio.timeout(settings.query_timeout_seconds):
                async with await self._connect() as conn:
                    async with conn.cursor() as cur:
                        # Statement-level timeout as an inner-layer defense.
                        await cur.execute(
                            "SET LOCAL statement_timeout = %s",
                            (settings.query_timeout_seconds * 1000,),
                        )
                        await cur.execute(safe_sql)
                        columns = (
                            [d.name for d in cur.description] if cur.description else []
                        )
                        fetched = await cur.fetchmany(settings.max_result_rows + 1)
                        truncated = len(fetched) > settings.max_result_rows
                        rows = [
                            tuple(row[c] for c in columns)
                            for row in fetched[: settings.max_result_rows]
                        ]
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
        # Nothing persistent — connections are per-call.
        return None


def _split_qualified(table: str, default_schema: str) -> tuple[str, str]:
    """Split "schema.table" or "table" into (schema, table)."""
    if "." in table:
        schema, name = table.split(".", 1)
        return schema.strip('"'), name.strip('"')
    return default_schema, table.strip('"')


def _qualify(schema: str | None, name: str) -> str:
    return f"{schema}.{name}" if schema else name


# Type-check: ensure adapter satisfies protocol.
_: DBAdapter = PostgresAdapter.__new__(PostgresAdapter)  # type: ignore[assignment]
