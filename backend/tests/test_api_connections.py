"""FastAPI /connections endpoint tests.

We reset the registry per test with a FakeEmbedder so no ML model loads and
no ChromaDB persistence bleeds between tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.registry import reset_registry_for_tests
from app.main import app
from app.rag.embedder import FakeEmbedder


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_registry_for_tests(embedder=FakeEmbedder(dimension=64))
    yield
    reset_registry_for_tests(embedder=FakeEmbedder(dimension=64))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_ok(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_register_sqlite_via_upload(client: TestClient, sample_sqlite_path: Path):
    with sample_sqlite_path.open("rb") as fh:
        r = client.post(
            "/connections/sqlite",
            files={"file": ("shop.sqlite", fh, "application/octet-stream")},
            data={"label": "shop"},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "sqlite"
    assert body["label"] == "shop"
    assert body["connection_id"].startswith("sqlite:")

    listed = client.get("/connections").json()
    assert any(c["connection_id"] == body["connection_id"] for c in listed["connections"])


def test_register_sqlite_rejects_empty_upload(client: TestClient):
    r = client.post(
        "/connections/sqlite",
        files={"file": ("empty.sqlite", b"", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_register_postgres_surfaces_connection_error(client: TestClient):
    # Point at an obviously unreachable host so psycopg fails fast.
    r = client.post(
        "/connections/postgres",
        json={"conninfo": "host=127.0.0.1 port=1 user=nobody dbname=nope connect_timeout=1"},
    )
    assert r.status_code == 400
    assert "Failed to register Postgres" in r.json()["detail"]


def test_unregister_missing_returns_404(client: TestClient):
    r = client.delete("/connections/does-not-exist")
    assert r.status_code == 404


def test_unregister_removes_connection(client: TestClient, sample_sqlite_path: Path):
    with sample_sqlite_path.open("rb") as fh:
        cid = client.post(
            "/connections/sqlite",
            files={"file": ("shop.sqlite", fh, "application/octet-stream")},
        ).json()["connection_id"]

    assert client.delete(f"/connections/{cid}").status_code == 204
    listed = client.get("/connections").json()
    assert all(c["connection_id"] != cid for c in listed["connections"])
