"""Connection registration endpoints.

Two ways to register a database:
  POST /connections/sqlite   — multipart .sqlite upload
  POST /connections/postgres — JSON body with conninfo

Both auto-index the schema on registration (via ConnectionRegistry.register),
so /ask is usable immediately after.

Uploaded SQLite files are persisted in `data/uploads/` under a unique name.
We keep the file on disk because SQLiteAdapter opens the URI on every query.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from app.api.deps import registry_dep
from app.db.registry import ConnectionConfig, ConnectionRegistry
from app.models.api import (
    ConnectionInfo,
    ConnectionListResponse,
    RegisterPostgresRequest,
)

router = APIRouter(prefix="/connections", tags=["connections"])

UPLOAD_DIR = Path("data/uploads")


@router.post("/sqlite", response_model=ConnectionInfo, status_code=201)
async def register_sqlite(
    file: UploadFile = File(...),
    label: str | None = Form(default=None),
    registry: ConnectionRegistry = Depends(registry_dep),
) -> ConnectionInfo:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Prefix with a uuid so two uploads of the same-named file don't collide.
    dest = UPLOAD_DIR / f"{uuid4().hex[:8]}_{Path(file.filename).name}"
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    dest.write_bytes(contents)

    try:
        connection_id = await registry.register(
            ConnectionConfig(kind="sqlite", sqlite_path=str(dest), label=label)
        )
    except Exception as e:
        # Roll back the file on any indexing failure so we don't leak junk.
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to register SQLite: {e}") from e

    return ConnectionInfo(connection_id=connection_id, kind="sqlite", label=label)


@router.post("/postgres", response_model=ConnectionInfo, status_code=201)
async def register_postgres(
    body: RegisterPostgresRequest,
    registry: ConnectionRegistry = Depends(registry_dep),
) -> ConnectionInfo:
    try:
        connection_id = await registry.register(
            ConnectionConfig(
                kind="postgres",
                postgres_conninfo=body.conninfo,
                label=body.label,
            )
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to register Postgres: {e}") from e

    return ConnectionInfo(connection_id=connection_id, kind="postgres", label=body.label)


@router.get("", response_model=ConnectionListResponse)
async def list_connections(
    registry: ConnectionRegistry = Depends(registry_dep),
) -> ConnectionListResponse:
    return ConnectionListResponse(
        connections=[
            ConnectionInfo(connection_id=cid, kind=cfg.kind, label=cfg.label)
            for cid, cfg in registry.list()
        ]
    )


@router.delete("/{connection_id}", status_code=204, response_class=Response)
async def unregister(
    connection_id: str,
    registry: ConnectionRegistry = Depends(registry_dep),
) -> Response:
    try:
        registry.get(connection_id)  # confirm it exists
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await registry.unregister(connection_id)
    return Response(status_code=204)
