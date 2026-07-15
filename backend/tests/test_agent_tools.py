"""AgentTools — the 4 tools the LLM sees, wired to a real SQLite connection."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.tools import TOOL_SCHEMAS, AgentTools
from app.db.registry import (
    ConnectionConfig,
    get_registry,
    reset_registry_for_tests,
)
from app.rag.embedder import FakeEmbedder


@pytest.fixture
async def bound_tools(sample_sqlite_path: Path) -> AgentTools:
    reset_registry_for_tests(embedder=FakeEmbedder(dimension=64))
    reg = get_registry()
    cid = await reg.register(
        ConnectionConfig(kind="sqlite", sqlite_path=str(sample_sqlite_path))
    )
    return AgentTools(registry=reg, connection_id=cid)


# ---------- tool schema shape ----------


class TestToolSchemas:
    def test_all_four_tools_declared(self):
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        assert names == {
            "retrieve_tables",
            "get_sample_rows",
            "get_table_relationships",
            "execute_sql",
        }

    def test_every_tool_has_openai_shape(self):
        for t in TOOL_SCHEMAS:
            assert t["type"] == "function"
            fn = t["function"]
            assert isinstance(fn["name"], str)
            assert isinstance(fn["description"], str) and fn["description"].strip()
            assert fn["parameters"]["type"] == "object"

    def test_required_params_listed(self):
        by_name = {t["function"]["name"]: t["function"] for t in TOOL_SCHEMAS}
        assert by_name["retrieve_tables"]["parameters"]["required"] == ["question"]
        assert by_name["get_sample_rows"]["parameters"]["required"] == ["table"]
        assert by_name["execute_sql"]["parameters"]["required"] == ["sql"]
        # relationships takes no args
        assert "required" not in by_name["get_table_relationships"]["parameters"]


# ---------- retrieve_tables ----------


class TestRetrieveTables:
    async def test_returns_at_least_one_table(self, bound_tools: AgentTools):
        out = await bound_tools.retrieve_tables(question="customers", k=2)
        assert "tables" in out and len(out["tables"]) >= 1
        first = out["tables"][0]
        assert "name" in first and "signature" in first and "score" in first

    async def test_k_bounded(self, bound_tools: AgentTools):
        # Only 2 tables in the fixture; asking for 100 should not crash.
        out = await bound_tools.retrieve_tables(question="anything", k=100)
        assert len(out["tables"]) == 2

    async def test_k_minimum_one(self, bound_tools: AgentTools):
        out = await bound_tools.retrieve_tables(question="orders", k=0)
        assert len(out["tables"]) == 1


# ---------- get_sample_rows ----------


class TestGetSampleRows:
    async def test_returns_rows_and_columns(self, bound_tools: AgentTools):
        out = await bound_tools.get_sample_rows(table="customers", limit=2)
        assert set(out["columns"]) == {"id", "name", "email", "country"}
        assert 1 <= len(out["rows"]) <= 2
        assert out["row_count"] == len(out["rows"])

    async def test_unknown_table_returns_error_not_raise(self, bound_tools: AgentTools):
        out = await bound_tools.get_sample_rows(table="no_such_table")
        assert "error" in out
        assert out["error_type"] in {"UnsafeSQLError", "OperationalError"} or out[
            "error_type"
        ].endswith("Error")

    async def test_limit_capped(self, bound_tools: AgentTools):
        out = await bound_tools.get_sample_rows(table="orders", limit=999)
        # There are 4 rows in the fixture; limit is capped at 10, real result <= 4.
        assert len(out["rows"]) <= 10


# ---------- get_table_relationships ----------


class TestGetTableRelationships:
    async def test_finds_customer_order_fk(self, bound_tools: AgentTools):
        out = await bound_tools.get_table_relationships()
        fks = out["foreign_keys"]
        assert any(
            fk["from_table"] == "orders"
            and fk["from_column"] == "customer_id"
            and fk["to_table"] == "customers"
            and fk["to_column"] == "id"
            for fk in fks
        )


# ---------- execute_sql ----------


class TestExecuteSql:
    async def test_happy_path(self, bound_tools: AgentTools):
        out = await bound_tools.execute_sql(sql="SELECT id, name FROM customers ORDER BY id")
        assert "error" not in out
        assert out["columns"] == ["id", "name"]
        assert len(out["rows"]) == 3
        assert out["sql"].startswith("SELECT")

    async def test_syntax_error_returned_as_observation(self, bound_tools: AgentTools):
        out = await bound_tools.execute_sql(sql="SELECT FROM WHERE")
        assert "error" in out
        # sqlglot rejects malformed SQL at the safety layer.
        assert out["error_type"] in {"UnsafeSQLError", "OperationalError"}

    async def test_write_rejected_by_safety_layer(self, bound_tools: AgentTools):
        out = await bound_tools.execute_sql(sql="DROP TABLE customers")
        assert out["error_type"] == "UnsafeSQLError"
        assert "SQL rejected" in out["error"]

    async def test_empty_sql_rejected(self, bound_tools: AgentTools):
        out = await bound_tools.execute_sql(sql="   ")
        assert out["error_type"] == "ValueError"


# ---------- dispatch ----------


class TestDispatch:
    async def test_routes_by_name(self, bound_tools: AgentTools):
        out = await bound_tools.dispatch(
            "execute_sql", {"sql": "SELECT COUNT(*) AS n FROM orders"}
        )
        assert out["columns"] == ["n"]
        assert out["rows"][0][0] == 4

    async def test_unknown_tool_returns_observation(self, bound_tools: AgentTools):
        out = await bound_tools.dispatch("summon_dragon", {})
        assert out["error_type"] == "UnknownTool"
        assert "execute_sql" in out["error"]  # lists available tools

    async def test_bad_arguments_returned_as_observation(self, bound_tools: AgentTools):
        # missing required "sql" arg
        out = await bound_tools.dispatch("execute_sql", {})
        assert out["error_type"] == "BadArguments"


# ---------- JSON-safe row coercion ----------


class TestJsonableRows:
    async def test_dates_stringified(self, bound_tools: AgentTools):
        # created_at is stored as TEXT in the fixture, so it's already a string.
        # This test just guards that whatever we return survives json.dumps.
        import json as _json

        out = await bound_tools.execute_sql(
            sql="SELECT created_at FROM orders ORDER BY created_at LIMIT 1"
        )
        _json.dumps(out)  # must not raise
