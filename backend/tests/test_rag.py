"""Schema RAG tests.

Two layers:
  1. Unit tests with FakeEmbedder — always run, fast, no ML deps loaded.
  2. Real-model e2e — marked slow, opt-in via `pytest -m slow`.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from app.db.base import ColumnInfo, TableInfo
from app.db.sqlite import SQLiteAdapter
from app.rag.embedder import FakeEmbedder, _tokenize, _unit
from app.rag.schema_index import SchemaIndex, build_table_document


# -------- Document formatting --------


class TestBuildTableDocument:
    def test_document_includes_table_name(self):
        t = TableInfo(name="customers", columns=[])
        doc = build_table_document(t)
        assert "Table: customers" in doc

    def test_document_qualifies_with_schema_when_present(self):
        t = TableInfo(name="users", columns=[], schema="analytics")
        assert "Table: analytics.users" in build_table_document(t)

    def test_document_lists_column_names_and_types(self):
        t = TableInfo(
            name="orders",
            columns=[
                ColumnInfo(name="id", type="INTEGER", nullable=False, primary_key=True),
                ColumnInfo(name="customer_id", type="INTEGER", nullable=False),
                ColumnInfo(name="total", type="REAL", nullable=False),
            ],
        )
        doc = build_table_document(t)
        assert "id (integer)" in doc
        assert "customer_id (integer)" in doc
        assert "total (real)" in doc

    def test_description_appended_when_present(self):
        t = TableInfo(
            name="orders",
            columns=[],
            description="One row per completed purchase",
        )
        assert "One row per completed purchase" in build_table_document(t)


# -------- FakeEmbedder sanity --------


class TestFakeEmbedder:
    def test_dimension_matches_config(self):
        e = FakeEmbedder(dimension=16)
        assert e.dimension == 16
        [vec] = e.embed(["hello"])
        assert len(vec) == 16

    def test_deterministic(self):
        e = FakeEmbedder()
        [a] = e.embed(["orders table"])
        [b] = e.embed(["orders table"])
        assert a == b

    def test_normalized_to_unit_length(self):
        e = FakeEmbedder()
        [v] = e.embed(["customers"])
        norm = sum(x * x for x in v) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_similar_text_more_similar_than_dissimilar(self):
        e = FakeEmbedder(dimension=128)
        [target, close, far] = e.embed(
            [
                "customers table with name email country",
                "customers table with name email country region",
                "unrelated inventory warehouse shipment logistics",
            ]
        )
        sim_close = sum(a * b for a, b in zip(target, close))
        sim_far = sum(a * b for a, b in zip(target, far))
        assert sim_close > sim_far

    def test_tokenize_lowercases_and_splits(self):
        assert _tokenize("Order_ID DATE_created") == ["order", "id", "date", "created"]

    def test_unit_zero_vec_returns_zero_vec(self):
        assert _unit([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]


# -------- SchemaIndex + real SQLite adapter --------


@pytest.fixture
def wide_sqlite_path() -> Iterator[Path]:
    """SQLite with a wider schema than the base fixture — needed for real RAG tests."""
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            country TEXT
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            total REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            sku TEXT UNIQUE,
            name TEXT NOT NULL,
            unit_price REAL NOT NULL
        );
        CREATE TABLE inventory (
            product_id INTEGER PRIMARY KEY,
            warehouse_code TEXT NOT NULL,
            quantity_on_hand INTEGER NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE shipments (
            id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL,
            carrier TEXT NOT NULL,
            tracking_number TEXT,
            shipped_at TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );
        CREATE TABLE employees (
            id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            department TEXT,
            salary REAL
        );
        """
    )
    conn.commit()
    conn.close()
    yield path
    path.unlink(missing_ok=True)


async def test_index_schema_stores_every_table(wide_sqlite_path: Path):
    adapter = SQLiteAdapter(wide_sqlite_path, connection_id="idx_stores_every")
    index = SchemaIndex(
        connection_id=adapter.connection_id,
        embedder=FakeEmbedder(dimension=64),
    )
    count = await index.index_schema(adapter)
    assert count == 6
    assert index.table_count() == 6


async def test_retrieve_ranks_relevant_table_first(wide_sqlite_path: Path):
    adapter = SQLiteAdapter(wide_sqlite_path, connection_id="idx_ranks_first")
    index = SchemaIndex(
        connection_id=adapter.connection_id,
        embedder=FakeEmbedder(dimension=128),
    )
    await index.index_schema(adapter)

    hits = index.retrieve("which employees are in each department", k=3)
    assert hits, "retrieve should return at least one hit"
    assert hits[0].table.name == "employees"


async def test_retrieve_k_bounded_by_index_size(wide_sqlite_path: Path):
    adapter = SQLiteAdapter(wide_sqlite_path, connection_id="idx_k_bounded")
    index = SchemaIndex(
        connection_id=adapter.connection_id,
        embedder=FakeEmbedder(),
    )
    await index.index_schema(adapter)
    # Ask for more than we have — should still cap gracefully.
    hits = index.retrieve("something", k=100)
    assert len(hits) == 6


async def test_retrieve_before_index_returns_empty(wide_sqlite_path: Path):
    index = SchemaIndex(
        connection_id="empty_before_index",
        embedder=FakeEmbedder(),
    )
    assert index.retrieve("customers", k=5) == []


async def test_reindex_replaces_previous_content(wide_sqlite_path: Path):
    adapter = SQLiteAdapter(wide_sqlite_path, connection_id="idx_reindex")
    embedder = FakeEmbedder()
    index = SchemaIndex(connection_id=adapter.connection_id, embedder=embedder)

    await index.index_schema(adapter)
    first = index.table_count()

    # Re-index with same adapter — count must not double.
    index2 = SchemaIndex(connection_id=adapter.connection_id, embedder=embedder)
    await index2.index_schema(adapter)
    assert index2.table_count() == first


# -------- Real-model e2e (opt-in) --------


@pytest.mark.slow
async def test_bge_real_model_ranks_relevant_first(wide_sqlite_path: Path):
    """Loads BAAI/bge-small-en-v1.5 — slow, needs internet on first run."""
    from app.rag.embedder import SentenceTransformerEmbedder

    adapter = SQLiteAdapter(wide_sqlite_path, connection_id="bge_real_e2e")
    index = SchemaIndex(
        connection_id=adapter.connection_id,
        embedder=SentenceTransformerEmbedder(),
    )
    await index.index_schema(adapter)

    hits = index.retrieve("what did each customer buy last month", k=3)
    top_names = [h.table.name for h in hits]
    assert "orders" in top_names or "customers" in top_names
