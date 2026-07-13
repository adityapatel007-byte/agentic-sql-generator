"""Pytest fixtures — small in-memory SQLite for the adapter tests."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture
def sample_sqlite_path() -> Iterator[Path]:
    """Create a temp SQLite file with a tiny e-commerce schema and yield the path."""
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
        INSERT INTO customers (id, name, email, country) VALUES
            (1, 'Alice',   'alice@example.com',   'US'),
            (2, 'Bob',     'bob@example.com',     'IN'),
            (3, 'Charlie', 'charlie@example.com', 'US');
        INSERT INTO orders (id, customer_id, total, created_at) VALUES
            (100, 1,  49.99, '2026-06-01'),
            (101, 1, 120.00, '2026-06-15'),
            (102, 2,  15.50, '2026-06-20'),
            (103, 3, 200.00, '2026-07-01');
        """
    )
    conn.commit()
    conn.close()

    yield path

    path.unlink(missing_ok=True)
