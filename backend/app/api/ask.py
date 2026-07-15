"""Ask-a-question endpoint with SSE streaming.

POST /ask/{connection_id} — body: {"question": "..."}
Response: text/event-stream. Each SSE event has:
  event: <IterationEvent.type>   (one of: iteration, assistant, tool_call,
                                          tool_result, final)
  data: <json-encoded payload>

The last event is always `final`. Clients close the stream after seeing it.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.agent.loop import AgentLoop
from app.agent.provider import LLMProvider
from app.agent.tools import AgentTools
from app.api.deps import provider_dep, registry_dep
from app.config import settings
from app.db.registry import ConnectionRegistry
from app.models.api import AskRequest

router = APIRouter(tags=["ask"])


@router.post("/ask/{connection_id}")
async def ask(
    connection_id: str,
    body: AskRequest,
    registry: ConnectionRegistry = Depends(registry_dep),
    provider: LLMProvider = Depends(provider_dep),
) -> EventSourceResponse:
    try:
        tools = AgentTools(registry=registry, connection_id=connection_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    loop = AgentLoop(
        provider=provider,
        tools=tools,
        max_iterations=settings.max_agent_iterations,
    )

    async def stream() -> AsyncIterator[dict[str, Any]]:
        async for event in loop.astream(body.question):
            # sse-starlette dispatches on `event` and json-encodes `data`.
            yield {"event": event["type"], "data": json.dumps(event, default=str)}

    return EventSourceResponse(stream())
