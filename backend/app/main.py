"""FastAPI entrypoint.

Run with `uvicorn app.main:app --reload` from the backend/ directory.
Auth: none for v1 (single-user demo). Add before deploying.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ask, connections
from app.config import settings
from app.db.registry import get_registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # Close any open adapters on shutdown so we don't leak Postgres sockets.
    await get_registry().close_all()


app = FastAPI(
    title="Agentic SQL Generator",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(connections.router)
app.include_router(ask.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
