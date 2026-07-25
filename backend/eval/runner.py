"""Run the agentic loop over a list of EvalItems and score each.

Not a pytest fixture — this is the code the CLI uses to produce a real
baseline number. Tests inject a ScriptedProvider to run the same loop
without hitting the network.

DB registration is cached by sqlite_path so BIRD's many-questions-one-DB
layout doesn't re-index the same schema over and over.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agent.loop import AgentLoop
from app.agent.provider import LLMProvider
from app.agent.tools import AgentTools
from app.db.registry import ConnectionConfig, ConnectionRegistry
from app.rag.embedder import Embedder, FakeEmbedder

from .datasets import EvalItem
from .metrics import execution_accuracy


@dataclass
class EvalOutcome:
    item_id: str
    dataset: str
    db_id: str
    difficulty: str
    question: str
    gold_sql: str
    predicted_sql: str | None
    predicted_row_count: int | None
    gold_row_count: int | None
    correct: bool
    stop_reason: str
    iterations_used: int
    tool_calls: list[str] = field(default_factory=list)
    error: str | None = None  # runner-level (couldn't execute gold, etc.)
    elapsed_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalSummary:
    dataset: str
    model: str
    total: int
    correct: int
    accuracy: float
    avg_iterations: float
    by_difficulty: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProgressCb = Callable[[int, int, EvalOutcome], None]


async def run_items(
    items: Iterable[EvalItem],
    provider: LLMProvider,
    *,
    embedder: Embedder | None = None,
    max_iterations: int = 5,
    on_item: ProgressCb | None = None,
) -> list[EvalOutcome]:
    """Score every item. Returns outcomes in input order.

    We build a private ConnectionRegistry so we don't disturb any live
    FastAPI process. Same-path DBs are registered once and reused.
    """
    reg = ConnectionRegistry(embedder=embedder or FakeEmbedder(dimension=64))
    path_to_cid: dict[str, str] = {}
    items_list = list(items)
    total = len(items_list)
    outcomes: list[EvalOutcome] = []

    try:
        for idx, item in enumerate(items_list, start=1):
            outcome = await _run_one(reg, path_to_cid, item, provider, max_iterations)
            outcomes.append(outcome)
            if on_item is not None:
                on_item(idx, total, outcome)
    finally:
        await reg.close_all()

    return outcomes


async def _run_one(
    reg: ConnectionRegistry,
    path_to_cid: dict[str, str],
    item: EvalItem,
    provider: LLMProvider,
    max_iterations: int,
) -> EvalOutcome:
    t0 = time.perf_counter()

    cid = path_to_cid.get(item.sqlite_path)
    if cid is None:
        try:
            cid = await reg.register(
                ConnectionConfig(kind="sqlite", sqlite_path=item.sqlite_path)
            )
        except Exception as e:  # noqa: BLE001
            return EvalOutcome(
                item_id=item.id,
                dataset=item.dataset,
                db_id=item.db_id,
                difficulty=item.difficulty,
                question=item.question,
                gold_sql=item.gold_sql,
                predicted_sql=None,
                predicted_row_count=None,
                gold_row_count=None,
                correct=False,
                stop_reason="registry_error",
                iterations_used=0,
                error=f"register({item.sqlite_path}): {type(e).__name__}: {e}",
                elapsed_s=time.perf_counter() - t0,
            )
        path_to_cid[item.sqlite_path] = cid

    adapter = reg.get(cid)
    tools = AgentTools(registry=reg, connection_id=cid)
    loop = AgentLoop(provider=provider, tools=tools, max_iterations=max_iterations)

    # Compute gold rows first — a broken gold means the item is unscorable,
    # and we want to distinguish that from a model failure.
    try:
        gold_result = await adapter.execute_read(item.gold_sql)
    except Exception as e:  # noqa: BLE001
        return EvalOutcome(
            item_id=item.id,
            dataset=item.dataset,
            db_id=item.db_id,
            difficulty=item.difficulty,
            question=item.question,
            gold_sql=item.gold_sql,
            predicted_sql=None,
            predicted_row_count=None,
            gold_row_count=None,
            correct=False,
            stop_reason="gold_sql_error",
            iterations_used=0,
            error=f"gold execute: {type(e).__name__}: {e}",
            elapsed_s=time.perf_counter() - t0,
        )
    gold_rows = [list(r) for r in gold_result.rows]

    agent_result = await loop.run(item.question)
    pred_rows = agent_result.final_rows

    tool_calls = [
        f"{s.tool_name}({_shorten_args(s.tool_arguments)})"
        for s in agent_result.trace
        if s.kind == "tool_result" and s.tool_name
    ]

    correct = execution_accuracy(pred_rows, gold_rows, gold_sql=item.gold_sql)

    return EvalOutcome(
        item_id=item.id,
        dataset=item.dataset,
        db_id=item.db_id,
        difficulty=item.difficulty,
        question=item.question,
        gold_sql=item.gold_sql,
        predicted_sql=agent_result.final_sql,
        predicted_row_count=agent_result.row_count,
        gold_row_count=len(gold_rows),
        correct=correct,
        stop_reason=agent_result.stop_reason,
        iterations_used=agent_result.iterations_used,
        tool_calls=tool_calls,
        elapsed_s=time.perf_counter() - t0,
    )


def summarize(outcomes: list[EvalOutcome], *, dataset: str, model: str) -> EvalSummary:
    total = len(outcomes)
    correct = sum(1 for o in outcomes if o.correct)
    avg_iter = (sum(o.iterations_used for o in outcomes) / total) if total else 0.0

    by_diff: dict[str, dict[str, Any]] = {}
    for o in outcomes:
        bucket = by_diff.setdefault(o.difficulty, {"total": 0, "correct": 0})
        bucket["total"] += 1
        if o.correct:
            bucket["correct"] += 1
    for bucket in by_diff.values():
        bucket["accuracy"] = (
            bucket["correct"] / bucket["total"] if bucket["total"] else 0.0
        )

    return EvalSummary(
        dataset=dataset,
        model=model,
        total=total,
        correct=correct,
        accuracy=(correct / total) if total else 0.0,
        avg_iterations=avg_iter,
        by_difficulty=by_diff,
    )


def _shorten_args(args: dict[str, Any] | None, max_len: int = 60) -> str:
    if not args:
        return ""
    s = ", ".join(f"{k}={_short(v)}" for k, v in args.items())
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _short(v: Any, n: int = 40) -> str:
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"
