"""Tools the agent can call during a run.

Four tools, all thin wrappers over the DB adapter and schema index registered
for a specific connection_id:

  retrieve_tables         — RAG over the schema; agent's entry point
  get_sample_rows         — peek at real data shapes for a table
  get_table_relationships — foreign-key map for JOINs
  execute_sql             — run a read-only query; errors come back as
                            observations so the agent can self-correct

Every tool returns a JSON-serializable dict — no raw dataclasses, no
sqlalchemy row proxies. If something goes wrong we return
`{"error": ..., "error_type": ...}` instead of raising, so a bad SQL from
the model becomes a chance to retry, not a loop-terminating crash.
"""
from __future__ import annotations

import datetime as _dt
import decimal
from typing import Any

from app.db.base import DBAdapter, ForeignKey, QueryResult
from app.db.registry import ConnectionRegistry
from app.db.safety import UnsafeSQLError
from app.rag.schema_index import SchemaIndex

# OpenAI function-tool schemas — what the LLM sees.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_tables",
            "description": (
                "Semantic search over the database schema. Returns the top-k tables "
                "most relevant to a natural-language question, each with its column "
                "signature and a relevance score. Call this FIRST to figure out "
                "which tables you need before writing SQL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": (
                            "The user's question, or a rephrased version focused on "
                            "the entities and relationships you're looking for."
                        ),
                    },
                    "k": {
                        "type": "integer",
                        "description": "How many candidate tables to return (1-10).",
                        "default": 5,
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sample_rows",
            "description": (
                "Fetch a few rows from a specific table so you can see actual "
                "data shapes and values. Useful when column names alone don't "
                "make it obvious what a column contains."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": (
                            "Table name. Use 'schema.table' for Postgres when the "
                            "schema is not 'public'."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of rows to fetch (1-10).",
                        "default": 3,
                    },
                },
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_relationships",
            "description": (
                "List all foreign-key relationships. Use this to understand how "
                "tables JOIN before writing multi-table queries."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": (
                "Run a read-only SELECT (or WITH ... SELECT) and get rows back. "
                "Only SELECTs are allowed — writes and DDL will be rejected. "
                "If the query errors, you'll see the error and can fix and retry. "
                "This is how you produce the final answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A single SELECT statement.",
                    }
                },
                "required": ["sql"],
            },
        },
    },
]


class AgentTools:
    """Bound to one connection_id — the agent never chooses which DB to hit.

    We resolve the adapter and schema index up front so a missing connection
    fails fast at construction, not mid-run.
    """

    def __init__(self, registry: ConnectionRegistry, connection_id: str):
        self.connection_id = connection_id
        self._adapter: DBAdapter = registry.get(connection_id)
        self._index: SchemaIndex = registry.get_index(connection_id)

    async def retrieve_tables(self, question: str, k: int = 5) -> dict[str, Any]:
        k = max(1, min(int(k), 10))
        hits = self._index.retrieve(question, k=k)
        return {
            "tables": [
                {
                    "name": _qualified_name(h.table),
                    "signature": h.table.signature(),
                    "score": round(float(h.score), 4),
                }
                for h in hits
            ]
        }

    async def get_sample_rows(self, table: str, limit: int = 3) -> dict[str, Any]:
        limit = max(1, min(int(limit), 10))
        try:
            result = await self._adapter.get_sample_rows(table, limit=limit)
        except Exception as e:  # noqa: BLE001 — surface every failure as an observation
            return {"error": str(e), "error_type": type(e).__name__, "table": table}
        return _query_result_to_dict(result)

    async def get_table_relationships(self) -> dict[str, Any]:
        try:
            fks = await self._adapter.get_foreign_keys()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e), "error_type": type(e).__name__}
        return {"foreign_keys": [_fk_to_dict(fk) for fk in fks]}

    async def execute_sql(self, sql: str) -> dict[str, Any]:
        sql = sql.strip()
        if not sql:
            return {"error": "Empty SQL", "error_type": "ValueError", "sql": sql}
        try:
            result = await self._adapter.execute_read(sql)
        except UnsafeSQLError as e:
            return {
                "error": f"SQL rejected by safety layer: {e}",
                "error_type": "UnsafeSQLError",
                "sql": sql,
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e), "error_type": type(e).__name__, "sql": sql}
        return {**_query_result_to_dict(result), "sql": sql}

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route a tool_call to the right method. Bad name → observation, not crash."""
        handler = _HANDLERS.get(name)
        if handler is None:
            return {
                "error": f"Unknown tool: {name}. Available: {sorted(_HANDLERS)}",
                "error_type": "UnknownTool",
            }
        try:
            return await handler(self, arguments)
        except (TypeError, KeyError, ValueError) as e:
            # Bad arguments shape from the LLM (missing key, wrong type, non-int) —
            # surface it as an observation so the model can retry.
            return {
                "error": f"Bad arguments for {name}: {e}",
                "error_type": "BadArguments",
            }


async def _call_retrieve(self: AgentTools, args: dict[str, Any]) -> dict[str, Any]:
    return await self.retrieve_tables(
        question=str(args["question"]),
        k=int(args.get("k", 5)),
    )


async def _call_sample(self: AgentTools, args: dict[str, Any]) -> dict[str, Any]:
    return await self.get_sample_rows(
        table=str(args["table"]),
        limit=int(args.get("limit", 3)),
    )


async def _call_relationships(self: AgentTools, args: dict[str, Any]) -> dict[str, Any]:
    return await self.get_table_relationships()


async def _call_execute(self: AgentTools, args: dict[str, Any]) -> dict[str, Any]:
    return await self.execute_sql(sql=str(args["sql"]))


_HANDLERS = {
    "retrieve_tables": _call_retrieve,
    "get_sample_rows": _call_sample,
    "get_table_relationships": _call_relationships,
    "execute_sql": _call_execute,
}


def _qualified_name(table: Any) -> str:
    return f"{table.schema}.{table.name}" if getattr(table, "schema", None) else table.name


def _fk_to_dict(fk: ForeignKey) -> dict[str, str]:
    return {
        "from_table": fk.from_table,
        "from_column": fk.from_column,
        "to_table": fk.to_table,
        "to_column": fk.to_column,
    }


def _query_result_to_dict(result: QueryResult) -> dict[str, Any]:
    return {
        "columns": list(result.columns),
        "rows": [[_jsonable(v) for v in row] for row in result.rows],
        "row_count": result.row_count,
        "truncated": result.truncated,
        "elapsed_ms": round(result.elapsed_ms, 2),
    }


def _jsonable(value: Any) -> Any:
    """Coerce cell values into something json.dumps can handle."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return str(value)
