"""The generate → execute → observe → self-correct loop.

Each iteration:
  1. Ask the provider for the next assistant turn (may call tools or finish).
  2. If it calls tools, run each one, append the results as tool messages,
     and go around again.
  3. If it responds with plain text, we're done.

Hard cap at max_iterations so a stuck model can't burn credits forever.
Every successful execute_sql is remembered — even if the model rambles after,
we can still return the last query that actually worked.

Two entry points share the same loop body:
  - `astream(question)` yields dict events step-by-step for SSE.
  - `run(question)` consumes that stream and returns an AgentResult.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
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

    async def astream(self, question: str) -> AsyncIterator[dict[str, Any]]:
        """Yield typed dict events during the loop.

        Event `type` values, in wire order:
          iteration            — start of every iteration (before the provider call)
          assistant            — the model's turn (content may be None if it only tool-called)
          tool_call            — a tool the model wants to invoke
          tool_result          — the observation we're feeding back
          final                — terminal event, exactly once per run

        On provider failure we still emit `final` (success=False, stop_reason
        prefixed 'provider_error:') so clients see a well-typed terminator.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": question},
        ]
        last_success: dict[str, Any] | None = None
        last_content: str | None = None
        stop_reason = "max_iterations"
        iteration = 0

        for iteration in range(1, self._max_iterations + 1):
            yield {"type": "iteration", "iteration": iteration}

            try:
                resp = await self._provider.chat(messages, tools=TOOL_SCHEMAS)
            except Exception as e:  # noqa: BLE001
                yield self._final_event(
                    success=last_success is not None,
                    stop_reason=f"provider_error: {type(e).__name__}: {e}",
                    iterations_used=iteration - 1,
                    last_success=last_success,
                    answer_text=last_content,
                )
                return

            messages.append(resp.raw_assistant_message)
            last_content = resp.content

            yield {
                "type": "assistant",
                "iteration": iteration,
                "content": resp.content,
                "has_tool_calls": bool(resp.tool_calls),
            }

            if not resp.tool_calls:
                stop_reason = "answered"
                break

            for tc in resp.tool_calls:
                yield {
                    "type": "tool_call",
                    "iteration": iteration,
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                }

                result = await self._tools.dispatch(tc.name, tc.arguments)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": json.dumps(result, default=str),
                    }
                )

                yield {
                    "type": "tool_result",
                    "iteration": iteration,
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "result": result,
                }

                if tc.name == "execute_sql" and "error" not in result:
                    last_success = result

        yield self._final_event(
            success=last_success is not None,
            stop_reason=stop_reason,
            iterations_used=iteration,
            last_success=last_success,
            answer_text=last_content,
        )

    async def run(self, question: str) -> AgentResult:
        """Consume astream() and reassemble an AgentResult (trace + metadata)."""
        trace: list[TraceStep] = []
        # tool_call and tool_result events share tool_call_id; we bridge the
        # args across the two events so tool_result trace steps carry them.
        pending_args: dict[str, dict[str, Any]] = {}
        final_payload: dict[str, Any] | None = None

        async for ev in self.astream(question):
            et = ev["type"]
            if et == "assistant":
                trace.append(
                    TraceStep(
                        iteration=ev["iteration"],
                        kind="assistant",
                        content=ev["content"],
                    )
                )
            elif et == "tool_call":
                pending_args[ev["tool_call_id"]] = ev["arguments"]
            elif et == "tool_result":
                trace.append(
                    TraceStep(
                        iteration=ev["iteration"],
                        kind="tool_result",
                        tool_name=ev["name"],
                        tool_arguments=pending_args.pop(ev["tool_call_id"], None),
                        tool_result=ev["result"],
                    )
                )
            elif et == "final":
                final_payload = ev

        assert final_payload is not None  # astream always ends in final
        return AgentResult(
            success=final_payload["success"],
            stop_reason=final_payload["stop_reason"],
            iterations_used=final_payload["iterations_used"],
            final_sql=final_payload["final_sql"],
            final_columns=final_payload["final_columns"],
            final_rows=final_payload["final_rows"],
            row_count=final_payload["row_count"],
            answer_text=final_payload["answer_text"],
            trace=trace,
        )

    @staticmethod
    def _final_event(
        *,
        success: bool,
        stop_reason: str,
        iterations_used: int,
        last_success: dict[str, Any] | None,
        answer_text: str | None,
    ) -> dict[str, Any]:
        ls = last_success or {}
        return {
            "type": "final",
            "success": success,
            "stop_reason": stop_reason,
            "iterations_used": iterations_used,
            "final_sql": ls.get("sql"),
            "final_columns": ls.get("columns"),
            "final_rows": ls.get("rows"),
            "row_count": ls.get("row_count"),
            "answer_text": answer_text,
        }


