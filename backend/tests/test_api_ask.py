"""FastAPI /ask/{connection_id} SSE tests.

We override the provider dependency with a ScriptedProvider so the loop runs
against a canned sequence. We parse the SSE stream by hand — it's just
`event: <name>\\ndata: <json>\\n\\n` blocks separated by blank lines.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import provider_dep
from app.db.registry import (
    ConnectionConfig,
    get_registry,
    reset_registry_for_tests,
)
from app.main import app
from app.rag.embedder import FakeEmbedder

# Reuse ScriptedProvider + response helpers from the loop tests.
from tests.test_agent_loop import ScriptedProvider, text_resp, tool_call_resp


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_registry_for_tests(embedder=FakeEmbedder(dimension=64))
    # sse-starlette lazily creates AppStatus.should_exit_event on the first
    # event loop it sees. TestClient spins a fresh loop per test, so we reset
    # the singleton to avoid "bound to a different event loop" errors.
    from sse_starlette.sse import AppStatus
    AppStatus.should_exit_event = None
    yield
    app.dependency_overrides.clear()
    AppStatus.should_exit_event = None
    reset_registry_for_tests(embedder=FakeEmbedder(dimension=64))


@pytest.fixture
async def connection_id(sample_sqlite_path: Path) -> str:
    reg = get_registry()
    return await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path))
    )


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    """Turn an SSE payload into [(event_name, decoded_json), ...]."""
    # Normalize CRLF so blocks always split on a bare \n\n.
    normalized = raw.replace("\r\n", "\n")
    events: list[tuple[str, dict]] = []
    for block in normalized.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        name: str | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if name is None or not data_lines:
            continue
        # sse-starlette pings send `event: ping` with a comment/data line;
        # skip pings so tests only look at agent-emitted events.
        if name == "ping":
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            payload = {"_raw": "\n".join(data_lines)}
        events.append((name, payload))
    return events


def _bind_provider(provider: ScriptedProvider) -> None:
    app.dependency_overrides[provider_dep] = lambda: provider


async def test_ask_streams_typed_events_in_order(connection_id: str):
    provider = ScriptedProvider(
        [
            tool_call_resp("retrieve_tables", {"question": "count customers"}, "tc1"),
            tool_call_resp("execute_sql", {"sql": "SELECT COUNT(*) AS n FROM customers"}, "tc2"),
            text_resp("There are 3 customers."),
        ]
    )
    _bind_provider(provider)

    with TestClient(app) as client, client.stream(
        "POST",
        f"/ask/{connection_id}",
        json={"question": "How many customers?"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        raw = "".join(resp.iter_text())

    events = _parse_sse(raw)
    names = [n for n, _ in events]

    # Two iterations of retrieve+execute+... then a final answer + final event.
    assert names[0] == "iteration"
    assert "tool_call" in names
    assert "tool_result" in names
    assert names[-1] == "final"

    final = events[-1][1]
    assert final["success"] is True
    assert final["stop_reason"] == "answered"
    assert final["final_sql"] == "SELECT COUNT(*) AS n FROM customers"
    assert final["final_rows"] == [[3]]
    assert final["answer_text"] == "There are 3 customers."


async def test_ask_final_event_reports_failure_when_max_iterations_hit(connection_id: str):
    # 20 canned tool calls means the loop cannot end via "answered" —
    # it'll cap out at MAX_AGENT_ITERATIONS.
    provider = ScriptedProvider(
        [tool_call_resp("execute_sql", {"sql": "SELECT 1"}, f"tc{i}") for i in range(20)]
    )
    _bind_provider(provider)

    with TestClient(app) as client, client.stream(
        "POST",
        f"/ask/{connection_id}",
        json={"question": "loop"},
    ) as resp:
        raw = "".join(resp.iter_text())

    events = _parse_sse(raw)
    final = next(payload for name, payload in events if name == "final")
    assert final["stop_reason"] == "max_iterations"
    # execute_sql SELECT 1 does succeed, so success is True but the reason is the cap.
    assert final["success"] is True


def test_ask_unknown_connection_returns_404():
    with TestClient(app) as client:
        r = client.post(
            "/ask/does-not-exist",
            json={"question": "hi"},
        )
    assert r.status_code == 404


async def test_ask_provider_error_still_emits_final(connection_id: str):
    class BoomProvider:
        async def chat(self, messages, tools=None, temperature=0.0):
            raise RuntimeError("upstream boom")

    app.dependency_overrides[provider_dep] = lambda: BoomProvider()

    with TestClient(app) as client, client.stream(
        "POST",
        f"/ask/{connection_id}",
        json={"question": "anything"},
    ) as resp:
        raw = "".join(resp.iter_text())

    events = _parse_sse(raw)
    final = next(payload for name, payload in events if name == "final")
    assert final["success"] is False
    assert final["stop_reason"].startswith("provider_error")
    assert "upstream boom" in final["stop_reason"]
