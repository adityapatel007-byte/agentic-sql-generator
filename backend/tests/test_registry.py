"""Connection registry — build adapters, look them up, unregister."""
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


async def test_register_sqlite_returns_id_and_stores_adapter(sample_sqlite_path: Path):
    reset_registry_for_tests()
    reg = get_registry()
    cid = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path), label="demo")
    )
    adapter = reg.get(cid)
    assert isinstance(adapter, SQLiteAdapter)
    assert adapter.connection_id == cid


async def test_get_unknown_raises(sample_sqlite_path: Path):
    reset_registry_for_tests()
    reg = get_registry()
    with pytest.raises(KeyError):
        reg.get("does-not-exist")


async def test_unregister_removes_entry(sample_sqlite_path: Path):
    reset_registry_for_tests()
    reg = get_registry()
    cid = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path))
    )
    await reg.unregister(cid)
    with pytest.raises(KeyError):
        reg.get(cid)


async def test_list_reports_registered_connections(sample_sqlite_path: Path):
    reset_registry_for_tests()
    reg = get_registry()
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


def test_build_adapter_rejects_bad_config():
    with pytest.raises(ValueError):
        build_adapter(ConnectionConfig(kind="sqlite"))  # missing sqlite_path
    with pytest.raises(ValueError):
        build_adapter(ConnectionConfig(kind="postgres"))  # missing conninfo
    with pytest.raises(ValueError):
        build_adapter(ConnectionConfig(kind="mysql"))  # type: ignore[arg-type]


def test_singleton_returns_same_instance():
    reset_registry_for_tests()
    a = get_registry()
    b = get_registry()
    assert a is b
    assert isinstance(a, ConnectionRegistry)
