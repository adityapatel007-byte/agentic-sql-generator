"""Connection registry — holds live DB adapters keyed by connection_id.

The API layer registers a connection once (upload SQLite / paste Postgres URL),
then the agent tools look it up by id on every call. Keeping this centralized
means the agent never sees credentials and cannot be tricked into targeting
a database it wasn't given.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.db.base import DBAdapter
from app.db.postgres import PostgresAdapter
from app.db.sqlite import SQLiteAdapter


SourceKind = Literal["sqlite", "postgres"]


@dataclass
class ConnectionConfig:
    kind: SourceKind
    # exactly one of these is set depending on kind
    sqlite_path: str | None = None
    postgres_conninfo: str | None = None
    # optional human-readable label the UI can show
    label: str | None = None


def build_adapter(config: ConnectionConfig, connection_id: str | None = None) -> DBAdapter:
    """Turn a ConnectionConfig into a live adapter. Fails fast on bad config."""
    if config.kind == "sqlite":
        if not config.sqlite_path:
            raise ValueError("sqlite kind requires sqlite_path")
        return SQLiteAdapter(Path(config.sqlite_path), connection_id=connection_id)
    if config.kind == "postgres":
        if not config.postgres_conninfo:
            raise ValueError("postgres kind requires postgres_conninfo")
        return PostgresAdapter(config.postgres_conninfo, connection_id=connection_id)
    raise ValueError(f"Unknown source kind: {config.kind}")


@dataclass
class _Entry:
    adapter: DBAdapter
    config: ConnectionConfig


@dataclass
class ConnectionRegistry:
    """In-process registry. Not persistent — restart wipes it (fine for v1).

    Thread-safety: guarded by an asyncio.Lock. Not process-safe; the FastAPI
    process is the single writer.
    """

    _entries: dict[str, _Entry] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def register(self, config: ConnectionConfig) -> str:
        """Build the adapter, store it, return its connection_id."""
        adapter = build_adapter(config)
        async with self._lock:
            self._entries[adapter.connection_id] = _Entry(adapter=adapter, config=config)
        return adapter.connection_id

    def get(self, connection_id: str) -> DBAdapter:
        entry = self._entries.get(connection_id)
        if entry is None:
            raise KeyError(f"Unknown connection_id: {connection_id}")
        return entry.adapter

    def describe(self, connection_id: str) -> ConnectionConfig:
        entry = self._entries.get(connection_id)
        if entry is None:
            raise KeyError(f"Unknown connection_id: {connection_id}")
        return entry.config

    def list(self) -> list[tuple[str, ConnectionConfig]]:
        return [(cid, e.config) for cid, e in self._entries.items()]

    async def unregister(self, connection_id: str) -> None:
        async with self._lock:
            entry = self._entries.pop(connection_id, None)
        if entry is not None:
            await entry.adapter.close()

    async def close_all(self) -> None:
        async with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for e in entries:
            await e.adapter.close()


# Single process-wide registry. FastAPI can inject this via Depends.
_registry: ConnectionRegistry | None = None


def get_registry() -> ConnectionRegistry:
    """Lazy singleton so tests can replace it via reset_registry_for_tests()."""
    global _registry
    if _registry is None:
        _registry = ConnectionRegistry()
    return _registry


def reset_registry_for_tests() -> None:
    """Test hook — never call from application code."""
    global _registry
    _registry = ConnectionRegistry()
