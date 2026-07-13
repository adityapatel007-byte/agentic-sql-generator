"""SQLite adapter — introspection + safe execution."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.db.safety import UnsafeSQLError
from app.db.sqlite import SQLiteAdapter


async def test_list_tables(sample_sqlite_path: Path):
    adapter = SQLiteAdapter(sample_sqlite_path)
    tables = await adapter.list_tables()
    names = {t.name for t in tables}
    assert names == {"customers", "orders"}

    customers = next(t for t in tables if t.name == "customers")
    col_names = [c.name for c in customers.columns]
    assert col_names == ["id", "name", "email", "country"]
    pk = next(c for c in customers.columns if c.primary_key)
    assert pk.name == "id"


async def test_foreign_keys(sample_sqlite_path: Path):
    adapter = SQLiteAdapter(sample_sqlite_path)
    fks = await adapter.get_foreign_keys()
    assert len(fks) == 1
    fk = fks[0]
    assert fk.from_table == "orders"
    assert fk.from_column == "customer_id"
    assert fk.to_table == "customers"
    assert fk.to_column == "id"


async def test_execute_read_returns_rows(sample_sqlite_path: Path):
    adapter = SQLiteAdapter(sample_sqlite_path)
    result = await adapter.execute_read("SELECT name FROM customers ORDER BY id")
    assert result.columns == ["name"]
    assert [r[0] for r in result.rows] == ["Alice", "Bob", "Charlie"]
    assert result.row_count == 3
    assert not result.truncated


async def test_execute_read_blocks_writes(sample_sqlite_path: Path):
    adapter = SQLiteAdapter(sample_sqlite_path)
    with pytest.raises(UnsafeSQLError):
        await adapter.execute_read("DELETE FROM customers")


async def test_sample_rows(sample_sqlite_path: Path):
    adapter = SQLiteAdapter(sample_sqlite_path)
    result = await adapter.get_sample_rows("orders", limit=2)
    assert result.row_count == 2
    assert result.columns == ["id", "customer_id", "total", "created_at"]


async def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        SQLiteAdapter("/tmp/nonexistent-db-file.sqlite")
