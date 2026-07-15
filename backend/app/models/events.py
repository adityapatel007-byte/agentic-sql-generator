"""Typed SSE event payloads emitted by /ask/{connection_id}.

Each event is JSON-serialized as the SSE `data:` field, with the SSE
`event:` field set to the value of the `type` discriminator. Clients can
switch on the event type and decode the matching model.

Wire order for a normal run:
  iteration -> (assistant_text | tool_call -> tool_result)* -> final

`final` is always the terminal event, even on failure (success=False).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IterationEvent(BaseModel):
    type: Literal["iteration"] = "iteration"
    iteration: int


class AssistantTextEvent(BaseModel):
    """Emitted for every assistant turn — content may be None when the model
    only issued tool_calls (kept for symmetry so clients can render 'thinking')."""

    type: Literal["assistant"] = "assistant"
    iteration: int
    content: str | None = None
    has_tool_calls: bool = False


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    iteration: int
    tool_call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    iteration: int
    tool_call_id: str
    name: str
    result: dict[str, Any]


class FinalEvent(BaseModel):
    """Terminal event — always emitted exactly once per run."""

    type: Literal["final"] = "final"
    success: bool
    stop_reason: str
    iterations_used: int
    final_sql: str | None = None
    final_columns: list[str] | None = None
    final_rows: list[list[Any]] | None = None
    row_count: int | None = None
    answer_text: str | None = None
