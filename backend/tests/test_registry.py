"""Connection registry — build adapters, look them up, unregister.

Registration triggers schema-indexing, so we inject a FakeEmbedder to keep
tests fast and free of ML dependencies.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.db.registry import (
    ConnectionConfig,
    ConnectionRegistry,
    build_adapter,
    get_registry,
    reset_registry_for_tests,
)
from app.db.sqlite import SQLiteAdapter
from app.rag.embedder import FakeEmbedder


def _fresh_registry():
    reset_registry_for_tests(embedder=FakeEmbedder(dimension=32))
    return get_registry()


async def test_register_sqlite_returns_id_and_stores_adapter(sample_sqlite_path: Path):
    reg = _fresh_registry()
    cid = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path), label="demo")
    )
    adapter = reg.get(cid)
    assert isinstance(adapter, SQLiteAdapter)
    assert adapter.connection_id == cid


async def test_register_also_builds_schema_index(sample_sqlite_path: Path):
    reg = _fresh_registry()
    cid = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path))
    )
    index = reg.get_index(cid)
    # The base fixture has 2 tables (customers, orders).
    assert index.table_count() == 2

    hits = index.retrieve("customers", k=2)
    top_names = {h.table.name for h in hits}
    assert "customers" in top_names


async def test_get_unknown_raises(sample_sqlite_path: Path):
    reg = _fresh_registry()
    with pytest.raises(KeyError):
        reg.get("does-not-exist")
    with pytest.raises(KeyError):
        reg.get_index("does-not-exist")


async def test_unregister_removes_entry(sample_sqlite_path: Path):
    reg = _fresh_registry()
    cid = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path))
    )
    await reg.unregister(cid)
    with pytest.raises(KeyError):
        reg.get(cid)


async def test_list_reports_registered_connections(sample_sqlite_path: Path):
    reg = _fresh_registry()
    cid1 = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path), label="a")
    )
    cid2 = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path), label="b")
    )
    listing = dict(reg.list())
    assert set(listing) == {cid1, cid2}
    assert listing[cid1].label == "a"
    assert listing[cid2].label == "b"


async def test_indexes_are_isolated_per_connection(sample_sqlite_path: Path):
    """A retrieve() on one connection must never surface another's tables."""
    reg = _fresh_registry()
    cid_a = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path), label="a")
    )
    cid_b = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path), label="b")
    )
    hits_a = reg.get_index(cid_a).retrieve("customers", k=5)
    hits_b = reg.get_index(cid_b).retrieve("customers", k=5)
    # Same schema, so both find the tables — but the indexes are separate objects.
    assert reg.get_index(cid_a) is not reg.get_index(cid_b)
    assert len(hits_a) > 0 and len(hits_b) > 0


def test_build_adapter_rejects_bad_config():
    with pytest.raises(ValueError):
        build_adapter(ConnectionConfig(kind="sqlite"))  # missing sqlite_path
    with pytest.raises(ValueError):
        build_adapter(ConnectionConfig(kind="postgres"))  # missing conninfo
    with pytest.raises(ValueError):
        build_adapter(ConnectionConfig(kind="mysql"))  # type: ignore[arg-type]


def test_singleton_returns_same_instance():
    reset_registry_for_tests(embedder=FakeEmbedder())
    a = get_registry()
    b = get_registry()
    assert a is b
    assert isinstance(a, ConnectionRegistry)
