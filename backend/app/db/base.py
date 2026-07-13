"""DB adapter protocol — every backend (SQLite, Postgres) implements this."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    primary_key: bool = False
    default: str | None = None


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo]
    schema: str | None = None  # for Postgres
    description: str | None = None  # user-provided or inferred

    def signature(self) -> str:
        """Compact signature used for RAG embeddings and prompt injection."""
        cols = ", ".join(f"{c.name} {c.type}" for c in self.columns)
        prefix = f"{self.schema}." if self.schema else ""
        return f"TABLE {prefix}{self.name} ({cols})"


@dataclass
class ForeignKey:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int
    truncated: bool
    elapsed_ms: float


class DBAdapter(Protocol):
    """Every DB backend implements these methods."""

    connection_id: str

    async def list_tables(self) -> list[TableInfo]: ...
    async def get_sample_rows(self, table: str, limit: int = 3) -> QueryResult: ...
    async def get_foreign_keys(self) -> list[ForeignKey]: ...
    async def execute_read(self, sql: str) -> QueryResult: ...
    async def close(self) -> None: ...
