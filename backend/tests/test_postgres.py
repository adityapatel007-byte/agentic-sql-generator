"""Postgres adapter tests.

Two layers:
  1. Postgres-dialect safety tests — always run, no DB needed.
  2. Live integration tests — skipped unless TEST_POSTGRES_URL is set.

To run the live tests locally:
  docker run --rm -d --name pg-test -p 5432:5432 -e POSTGRES_PASSWORD=pw postgres:16
  export TEST_POSTGRES_URL="postgresql://postgres:pw@localhost:5432/postgres"
  pytest tests/test_postgres.py
"""
from __future__ import annotations

import os

import pytest

from app.db.postgres import PostgresAdapter, _qualify, _split_qualified
from app.db.safety import UnsafeSQLError, assert_read_only


# -------- Postgres-dialect safety (no DB required) --------


class TestPostgresDialectSafety:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT 1",
            'SELECT * FROM "customers"',
            "SELECT * FROM customers OFFSET 5 LIMIT 10",
            "WITH t AS (SELECT id FROM customers) SELECT * FROM t",
            "SELECT jsonb_agg(o) FROM orders o",
        ],
    )
    def test_pg_selects_allowed(self, sql: str):
        assert assert_read_only(sql, dialect="postgres")

    @pytest.mark.parametrize(
        "sql",
        [
            "COPY customers TO STDOUT",
            "COPY customers FROM '/tmp/x.csv'",
            'CREATE TABLE foo (id INT)',
            'DROP TABLE customers',
            'ALTER TABLE customers ADD COLUMN evil TEXT',
            'TRUNCATE TABLE customers',
            'GRANT ALL ON customers TO evil',
            'VACUUM ANALYZE',
        ],
    )
    def test_pg_writes_and_admin_rejected(self, sql: str):
        with pytest.raises(UnsafeSQLError):
            assert_read_only(sql, dialect="postgres")

    def test_pg_multi_statement_rejected(self):
        with pytest.raises(UnsafeSQLError):
            assert_read_only("SELECT 1; DROP TABLE customers", dialect="postgres")


# -------- Helper unit tests (no DB required) --------


class TestHelpers:
    def test_split_qualified_with_schema(self):
        assert _split_qualified("public.users", default_schema="public") == ("public", "users")

    def test_split_qualified_without_schema_uses_default(self):
        assert _split_qualified("users", default_schema="analytics") == ("analytics", "users")

    def test_split_qualified_strips_quotes(self):
        assert _split_qualified('"public"."My Table"', default_schema="public") == (
            "public",
            "My Table",
        )

    def test_qualify_prepends_schema_when_present(self):
        assert _qualify("public", "users") == "public.users"

    def test_qualify_bare_when_schema_missing(self):
        assert _qualify(None, "users") == "users"


class TestAdapterConstruction:
    def test_empty_conninfo_rejected(self):
        with pytest.raises(ValueError):
            PostgresAdapter("")

    def test_connection_id_defaults_and_overrides(self):
        a = PostgresAdapter("host=x dbname=y")
        assert a.connection_id.startswith("postgres:")
        b = PostgresAdapter("host=x dbname=y", connection_id="custom-id")
        assert b.connection_id == "custom-id"


# -------- Live integration (skipped unless TEST_POSTGRES_URL is set) --------


TEST_PG_URL = os.environ.get("TEST_POSTGRES_URL")
live = pytest.mark.skipif(
    TEST_PG_URL is None,
    reason="Set TEST_POSTGRES_URL to a running Postgres to enable live tests",
)


@pytest.fixture
async def live_pg_adapter():
    """Bootstrap a temp schema on the target Postgres and yield an adapter."""
    import psycopg

    schema = f"sql_agent_test_{os.getpid()}"
    async with await psycopg.AsyncConnection.connect(TEST_PG_URL, autocommit=True) as setup:
        async with setup.cursor() as cur:
            await cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            await cur.execute(f"CREATE SCHEMA {schema}")
            await cur.execute(f"SET search_path TO {schema}")
            await cur.execute(
                """
                CREATE TABLE customers (
                    id INT PRIMARY KEY,
                    name TEXT NOT NULL,
                    country TEXT
                );
                CREATE TABLE orders (
                    id INT PRIMARY KEY,
                    customer_id INT NOT NULL REFERENCES customers(id),
                    total NUMERIC NOT NULL
                );
                INSERT INTO customers VALUES (1,'Alice','US'), (2,'Bob','IN');
                INSERT INTO orders    VALUES (100,1,49.99), (101,2,15.50);
                """
            )

    adapter = PostgresAdapter(TEST_PG_URL, include_schemas=(schema,))
    try:
        yield adapter
    finally:
        async with await psycopg.AsyncConnection.connect(TEST_PG_URL, autocommit=True) as tear:
            async with tear.cursor() as cur:
                await cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


@live
async def test_live_list_tables(live_pg_adapter):
    tables = await live_pg_adapter.list_tables()
    names = {t.name for t in tables}
    assert names == {"customers", "orders"}


@live
async def test_live_foreign_keys(live_pg_adapter):
    fks = await live_pg_adapter.get_foreign_keys()
    assert any(
        fk.from_column == "customer_id" and fk.to_column == "id" for fk in fks
    )


@live
async def test_live_execute_read(live_pg_adapter):
    result = await live_pg_adapter.execute_read("SELECT name FROM customers ORDER BY id")
    assert result.columns == ["name"]
    assert [r[0] for r in result.rows] == ["Alice", "Bob"]


@live
async def test_live_execute_read_blocks_writes(live_pg_adapter):
    with pytest.raises(UnsafeSQLError):
        await live_pg_adapter.execute_read("DELETE FROM customers")
