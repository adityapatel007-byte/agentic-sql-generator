"""FastAPI dependency providers.

Kept as thin functions so tests can override each via
`app.dependency_overrides[...] = lambda: ...`. Nothing in the endpoints
imports the concrete registry / provider — they only ask for the type.
"""
from __future__ import annotations

from app.agent.provider import LLMProvider, default_provider
from app.db.registry import ConnectionRegistry, get_registry


def registry_dep() -> ConnectionRegistry:
    return get_registry()


def provider_dep() -> LLMProvider:
    return default_provider()
