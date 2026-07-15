"""End-to-end smoke test against the real Nemotron 3 Nano endpoint.

Builds a tiny in-memory-style SQLite, registers it, wires the agent loop,
and asks a single question. Prints the full trace and final result so we can
eyeball whether the model actually calls tools in a sane order, self-corrects
on SQL errors, and returns something coherent.

Usage:
    cd backend
    python scripts/smoke_nemotron.py
    python scripts/smoke_nemotron.py "your custom question here"

Requires NVIDIA_API_KEY in backend/.env.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

# Make `app.*` importable when run directly (python scripts/smoke_nemotron.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent.loop import AgentLoop  # noqa: E402
from app.agent.provider import default_provider  # noqa: E402
from app.agent.tools import AgentTools  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.registry import (  # noqa: E402
    ConnectionConfig,
    get_registry,
    reset_registry_for_tests,
)
from app.rag.embedder import FakeEmbedder  # noqa: E402


SCHEMA_SQL = """
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


def build_sample_sqlite() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    path = Path(tmp.name)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    return path


def summarise_tool_result(name: str, result: dict) -> str:
    """One-line summary of a tool call's result for the trace print."""
    if "error" in result:
        return f"ERROR {result['error_type']}: {result['error'][:120]}"
    if name == "retrieve_tables":
        names = [t["name"] for t in result.get("tables", [])]
        return f"tables={names}"
    if name == "get_sample_rows":
        return f"cols={result.get('columns')} rows={result.get('row_count')}"
    if name == "get_table_relationships":
        return f"foreign_keys={len(result.get('foreign_keys', []))}"
    if name == "execute_sql":
        return f"cols={result.get('columns')} rows={result.get('row_count')}"
    return str(result)[:200]


async def main() -> int:
    question = sys.argv[1] if len(sys.argv) > 1 else "How many customers are in the US?"

    if not settings.nvidia_api_key:
        print("NVIDIA_API_KEY not set — put it in backend/.env", file=sys.stderr)
        return 2

    print(f"model      : {settings.default_model}")
    print(f"base_url   : {settings.nvidia_base_url}")
    print(f"question   : {question}")
    print("-" * 72)

    db_path = build_sample_sqlite()
    try:
        # FakeEmbedder keeps the smoke fast — the goal is to test the LLM, not RAG.
        reset_registry_for_tests(embedder=FakeEmbedder(dimension=64))
        reg = get_registry()
        cid = await reg.register(
            ConnectionConfig(kind="sqlite", sqlite_path=str(db_path), label="smoke")
        )

        tools = AgentTools(registry=reg, connection_id=cid)
        loop = AgentLoop(
            provider=default_provider(),
            tools=tools,
            max_iterations=settings.max_agent_iterations,
        )

        result = await loop.run(question)
    finally:
        db_path.unlink(missing_ok=True)

    print("TRACE")
    for step in result.trace:
        if step.kind == "assistant":
            preview = (step.content or "").strip().replace("\n", " ")
            print(f"  [iter {step.iteration}] assistant: {preview[:200]}")
        else:
            summary = summarise_tool_result(step.tool_name or "", step.tool_result or {})
            args_str = json.dumps(step.tool_arguments or {}, default=str)
            if len(args_str) > 120:
                args_str = args_str[:117] + "..."
            print(f"  [iter {step.iteration}] tool {step.tool_name}({args_str}) -> {summary}")

    print("-" * 72)
    print(f"success        : {result.success}")
    print(f"stop_reason    : {result.stop_reason}")
    print(f"iterations     : {result.iterations_used}")
    print(f"final_sql      : {result.final_sql}")
    if result.final_columns:
        print(f"final_columns  : {result.final_columns}")
    if result.final_rows is not None:
        preview_rows = result.final_rows[:5]
        print(f"final_rows[:5] : {preview_rows}  (total {result.row_count})")
    if result.answer_text:
        print(f"answer_text    : {result.answer_text.strip()}")

    return 0 if result.success else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
