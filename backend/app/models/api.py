"""Request/response bodies for the FastAPI layer.

Kept separate from the SSE event models in `events.py` so the ask-endpoint
stream schema can evolve without touching the connection endpoints.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RegisterPostgresRequest(BaseModel):
    conninfo: str = Field(..., description="Postgres connection string (libpq format)")
    label: str | None = Field(default=None, max_length=80)
    include_schemas: list[str] = Field(default_factory=lambda: ["public"])


class ConnectionInfo(BaseModel):
    connection_id: str
    kind: Literal["sqlite", "postgres"]
    label: str | None = None


class ConnectionListResponse(BaseModel):
    connections: list[ConnectionInfo]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class ErrorResponse(BaseModel):
    error: str
    error_type: str
