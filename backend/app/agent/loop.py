"""The generate → execute → observe → self-correct loop.

Each iteration:
  1. Ask the provider for the next assistant turn (may call tools or finish).
  2. If it calls tools, run each one, append the results as tool messages,
     and go around again.
  3. If it responds with plain text, we're done.

Hard cap at max_iterations so a stuck model can't burn credits forever.
Every successful execute_sql is remembered — even if the model rambles after,
we can still return the last query that actually worked.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.provider import LLMProvider
from app.agent.tools import TOOL_SCHEMAS, AgentTools

SYSTEM_PROMPT = """You are an expert SQL analyst answering questions about a user's database.

You have four tools:
  retrieve_tables         — semantic search over the schema. Start here.
  get_sample_rows         — peek at real values in a table when column names alone aren't enough.
  get_table_relationships — list foreign keys before writing JOINs.
  execute_sql             — run a read-only SELECT. Errors come back as observations you can fix.

Workflow:
  1. Call retrieve_tables with the user's question.
  2. If a column's meaning is unclear, call get_sample_rows for that table.
  3. For multi-table queries, call get_table_relationships to get the JOIN keys right.
  4. Call execute_sql with your SELECT. If it errors, read the error, correct your SQL,
     and call execute_sql again. Don't guess-and-hope — fix the specific issue.
  5. Once execute_sql succeeds, reply to the user in one or two sentences summarising
     what the query returned. Do not call more tools after that.

Rules:
  - Only SELECT (or WITH ... SELECT). Writes and DDL will be rejected.
  - Match table and column names exactly as they appear in retrieve_tables results.
  - Prefer explicit column lists over SELECT *.
  - If nothing in the schema can answer the question, say so plainly — don't invent tables.
"""


@dataclass
class TraceStep:
    """One entry in the run trace — enough to reconstruct what the agent did."""

    iteration: int
    kind: str  # "assistant" | "tool_result"
    content: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class AgentResult:
    success: bool
    stop_reason: str  # "answered" | "max_iterations" | "provider_error"
    iterations_used: int
    final_sql: str | None = None
    final_columns: list[str] | None = None
    final_rows: list[list[Any]] | None = None
    row_count: int | None = None
    answer_text: str | None = None
    trace: list[TraceStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trace"] = [step.to_dict() for step in self.trace]
        return d


class AgentLoop:
    def __init__(
        self,
        provider: LLMProvider,
        tools: AgentTools,
        max_iterations: int = 5,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self._provider = provider
        self._tools = tools
        self._max_iterations = max_iterations
        self._system_prompt = system_prompt

    async def run(self, question: str) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": question},
        ]
        trace: list[TraceStep] = []
        last_success: dict[str, Any] | None = None
        last_content: str | None = None
        stop_reason = "max_iterations"
        iteration = 0

        for iteration in range(1, self._max_iterations + 1):
            try:
                resp = await self._provider.chat(messages, tools=TOOL_SCHEMAS)
            except Exception as e:  # noqa: BLE001
                return AgentResult(
                    success=last_success is not None,
                    stop_reason=f"provider_error: {type(e).__name__}: {e}",
                    iterations_used=iteration - 1,
                    final_sql=(last_success or {}).get("sql"),
                    final_columns=(last_success or {}).get("columns"),
                    final_rows=(last_success or {}).get("rows"),
                    row_count=(last_success or {}).get("row_count"),
                    answer_text=last_content,
                    trace=trace,
                )

            messages.append(resp.raw_assistant_message)
            last_content = resp.content
            trace.append(
                TraceStep(
                    iteration=iteration,
                    kind="assistant",
                    content=resp.content,
                )
            )

            if not resp.tool_calls:
                stop_reason = "answered"
                break

            for tc in resp.tool_calls:
                result = await self._tools.dispatch(tc.name, tc.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": json.dumps(result, default=str),
                    }
                )
                trace.append(
                    TraceStep(
                        iteration=iteration,
                        kind="tool_result",
                        tool_name=tc.name,
                        tool_arguments=tc.arguments,
                        tool_result=result,
                    )
                )
                if tc.name == "execute_sql" and "error" not in result:
                    last_success = result

        return AgentResult(
            success=last_success is not None,
            stop_reason=stop_reason,
            iterations_used=iteration,
            final_sql=(last_success or {}).get("sql"),
            final_columns=(last_success or {}).get("columns"),
            final_rows=(last_success or {}).get("rows"),
            row_count=(last_success or {}).get("row_count"),
            answer_text=last_content,
            trace=trace,
        )
