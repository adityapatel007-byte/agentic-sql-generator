"""Agentic loop — generate/execute/observe/correct cycle.

We inject a ScriptedProvider so tests don't need an LLM. Every test verifies
a specific behaviour of the loop: happy path, self-correction, iteration cap,
read-only enforcement propagating, provider errors handled cleanly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.agent.loop import AgentLoop
from app.agent.provider import ProviderResponse, ToolCall
from app.agent.tools import AgentTools
from app.db.registry import (
    ConnectionConfig,
    get_registry,
    reset_registry_for_tests,
)
from app.rag.embedder import FakeEmbedder

# ---------- helpers ----------


def tool_call_resp(name: str, arguments: dict[str, Any], tool_id: str = "tc1") -> ProviderResponse:
    """Build a ProviderResponse that issues a single tool call."""
    return ProviderResponse(
        content=None,
        tool_calls=[ToolCall(id=tool_id, name=name, arguments=arguments)],
        raw_assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(arguments),
                    },
                }
            ],
        },
        finish_reason="tool_calls",
    )


def text_resp(text: str) -> ProviderResponse:
    """Build a ProviderResponse that finishes with plain text."""
    return ProviderResponse(
        content=text,
        tool_calls=[],
        raw_assistant_message={"role": "assistant", "content": text},
        finish_reason="stop",
    )


@dataclass
class ScriptedProvider:
    """Yields pre-set responses in order. Records every call for assertions."""

    responses: list[ProviderResponse]
    calls: list[dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.calls = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> ProviderResponse:
        # Snapshot messages so later mutation doesn't affect the record.
        self.calls.append(
            {
                "messages": [dict(m) for m in messages],
                "tool_names": [t["function"]["name"] for t in (tools or [])],
            }
        )
        if not self.responses:
            raise AssertionError("ScriptedProvider script exhausted")
        return self.responses.pop(0)


class BoomProvider:
    """Provider that always raises — models a network failure."""

    async def chat(self, messages, tools=None, temperature=0.0):
        raise RuntimeError("upstream boom")


@pytest.fixture
async def tools_ctx(sample_sqlite_path: Path) -> AgentTools:
    reset_registry_for_tests(embedder=FakeEmbedder(dimension=64))
    reg = get_registry()
    cid = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path))
    )
    return AgentTools(registry=reg, connection_id=cid)


# ---------- happy path ----------


async def test_happy_path_retrieve_then_execute_then_answer(tools_ctx: AgentTools):
    provider = ScriptedProvider(
        [
            tool_call_resp("retrieve_tables", {"question": "count customers"}, "tc1"),
            tool_call_resp(
                "execute_sql",
                {"sql": "SELECT COUNT(*) AS n FROM customers"},
                "tc2",
            ),
            text_resp("There are 3 customers."),
        ]
    )
    loop = AgentLoop(provider=provider, tools=tools_ctx, max_iterations=5)

    result = await loop.run("How many customers are there?")

    assert result.success is True
    assert result.stop_reason == "answered"
    assert result.final_sql == "SELECT COUNT(*) AS n FROM customers"
    assert result.final_columns == ["n"]
    assert result.final_rows == [[3]]
    assert result.row_count == 1
    assert result.answer_text == "There are 3 customers."
    assert result.iterations_used == 3


async def test_trace_records_every_turn(tools_ctx: AgentTools):
    provider = ScriptedProvider(
        [
            tool_call_resp("execute_sql", {"sql": "SELECT 1 AS x"}, "tc1"),
            text_resp("done"),
        ]
    )
    loop = AgentLoop(provider=provider, tools=tools_ctx, max_iterations=5)

    result = await loop.run("anything")

    kinds = [step.kind for step in result.trace]
    # assistant (tool_call) -> tool_result -> assistant (text)
    assert kinds == ["assistant", "tool_result", "assistant"]
    tool_step = result.trace[1]
    assert tool_step.tool_name == "execute_sql"
    assert tool_step.tool_result is not None
    assert tool_step.tool_result["columns"] == ["x"]


# ---------- self-correction ----------


async def test_self_corrects_after_sql_error(tools_ctx: AgentTools):
    """First execute_sql references a non-existent column; second one fixes it."""
    provider = ScriptedProvider(
        [
            tool_call_resp(
                "execute_sql",
                {"sql": "SELECT nope_column FROM customers"},
                "tc1",
            ),
            tool_call_resp(
                "execute_sql",
                {"sql": "SELECT name FROM customers ORDER BY name LIMIT 1"},
                "tc2",
            ),
            text_resp("Alice."),
        ]
    )
    loop = AgentLoop(provider=provider, tools=tools_ctx, max_iterations=5)

    result = await loop.run("who is the first customer alphabetically?")

    assert result.success is True
    assert result.final_sql == "SELECT name FROM customers ORDER BY name LIMIT 1"
    assert result.final_rows == [["Alice"]]
    # The bad SQL result should still appear in the trace so we can inspect it.
    bad_step = next(
        s for s in result.trace
        if s.tool_name == "execute_sql" and s.tool_result and "error" in s.tool_result
    )
    assert bad_step is not None


async def test_error_is_visible_in_messages_the_provider_sees(tools_ctx: AgentTools):
    """The error observation must reach the model, otherwise self-correction can't work."""
    provider = ScriptedProvider(
        [
            tool_call_resp("execute_sql", {"sql": "DROP TABLE customers"}, "tc1"),
            text_resp("I gave up."),
        ]
    )
    loop = AgentLoop(provider=provider, tools=tools_ctx, max_iterations=5)
    await loop.run("delete stuff")

    # Provider was called twice: initial + after tool result.
    assert len(provider.calls) == 2
    second_call_messages = provider.calls[1]["messages"]
    tool_msg = next(m for m in second_call_messages if m.get("role") == "tool")
    payload = json.loads(tool_msg["content"])
    assert payload["error_type"] == "UnsafeSQLError"


# ---------- iteration cap ----------


async def test_iteration_cap_enforced(tools_ctx: AgentTools):
    """Provider keeps calling tools forever; loop must stop at max_iterations."""
    provider = ScriptedProvider(
        [tool_call_resp("execute_sql", {"sql": "SELECT 1"}, f"tc{i}") for i in range(20)]
    )
    loop = AgentLoop(provider=provider, tools=tools_ctx, max_iterations=3)

    result = await loop.run("loop please")

    assert result.iterations_used == 3
    assert result.stop_reason == "max_iterations"
    # last successful execute_sql is still surfaced
    assert result.success is True
    assert result.final_columns == ["1"]


async def test_max_iterations_must_be_positive(tools_ctx: AgentTools):
    provider = ScriptedProvider([text_resp("hi")])
    with pytest.raises(ValueError):
        AgentLoop(provider=provider, tools=tools_ctx, max_iterations=0)


# ---------- edge cases ----------


async def test_model_answers_without_calling_tools_returns_unsuccessful(
    tools_ctx: AgentTools,
):
    """If the LLM refuses to execute anything, success=False but no crash."""
    provider = ScriptedProvider([text_resp("I don't know.")])
    loop = AgentLoop(provider=provider, tools=tools_ctx, max_iterations=5)

    result = await loop.run("no idea")

    assert result.success is False
    assert result.stop_reason == "answered"
    assert result.final_sql is None
    assert result.answer_text == "I don't know."
    assert result.iterations_used == 1


async def test_provider_error_returned_as_failure(tools_ctx: AgentTools):
    loop = AgentLoop(provider=BoomProvider(), tools=tools_ctx, max_iterations=5)
    result = await loop.run("anything")
    assert result.success is False
    assert result.stop_reason.startswith("provider_error")
    assert "upstream boom" in result.stop_reason


async def test_result_serializes_to_json(tools_ctx: AgentTools):
    provider = ScriptedProvider(
        [
            tool_call_resp("execute_sql", {"sql": "SELECT id FROM customers ORDER BY id"}, "tc1"),
            text_resp("done"),
        ]
    )
    loop = AgentLoop(provider=provider, tools=tools_ctx, max_iterations=5)
    result = await loop.run("ids")
    # to_dict should be json-safe end-to-end (rows, trace, everything).
    json.dumps(result.to_dict())
