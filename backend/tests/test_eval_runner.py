"""Eval runner + metrics — fast tests, no network, no real model."""
from __future__ import annotations

from pathlib import Path

import pytest

from eval.datasets import EvalItem, load_custom
from eval.metrics import (
    execution_accuracy,
    has_order_by,
    rows_equal_ordered,
    rows_equal_unordered,
)
from eval.runner import run_items, summarize
from tests.test_agent_loop import ScriptedProvider, text_resp, tool_call_resp

# ---------- metrics ----------


class TestHasOrderBy:
    def test_simple_order(self):
        assert has_order_by("SELECT id FROM t ORDER BY id")

    def test_no_order(self):
        assert not has_order_by("SELECT id FROM t")

    def test_order_inside_subquery_does_not_count(self):
        # Outer result set has no order — the subquery's ORDER BY is scoped to the CTE.
        sql = "WITH x AS (SELECT id FROM t ORDER BY id) SELECT id FROM x"
        assert not has_order_by(sql)

    def test_with_cte_outer_order(self):
        sql = "WITH x AS (SELECT id FROM t) SELECT id FROM x ORDER BY id"
        assert has_order_by(sql)

    def test_malformed_sql_is_treated_as_no_order(self):
        assert not has_order_by("this is not sql")


class TestRowEquality:
    def test_unordered_matches_regardless_of_row_order(self):
        assert rows_equal_unordered([[1], [2]], [[2], [1]])

    def test_unordered_respects_duplicates(self):
        # Multiset semantics: [1, 1, 2] != [1, 2, 2]
        assert not rows_equal_unordered([[1], [1], [2]], [[1], [2], [2]])

    def test_ordered_requires_same_order(self):
        assert rows_equal_ordered([[1], [2]], [[1], [2]])
        assert not rows_equal_ordered([[1], [2]], [[2], [1]])

    def test_float_tolerance(self):
        assert rows_equal_unordered([[1.00001]], [[1.00002]])  # both round to 1.0
        assert not rows_equal_unordered([[1.1]], [[1.2]])

    def test_none_cells(self):
        assert rows_equal_unordered([[1, None]], [[1, None]])
        assert not rows_equal_unordered([[1, None]], [[1, 0]])


class TestExecutionAccuracy:
    def test_gold_order_by_enforces_order_sensitivity(self):
        pred = [[2], [1]]
        gold = [[1], [2]]
        assert not execution_accuracy(pred, gold, gold_sql="SELECT id FROM t ORDER BY id")

    def test_gold_no_order_by_ignores_row_order(self):
        assert execution_accuracy(
            [[2], [1]], [[1], [2]], gold_sql="SELECT id FROM t"
        )

    def test_missing_prediction_is_incorrect(self):
        assert not execution_accuracy(None, [[1]], gold_sql="SELECT 1")


# ---------- runner ----------


@pytest.fixture
def two_item_set(sample_sqlite_path: Path) -> list[EvalItem]:
    return [
        EvalItem(
            id="test-count",
            dataset="custom",
            db_id="test",
            sqlite_path=str(sample_sqlite_path),
            question="how many customers?",
            gold_sql="SELECT COUNT(*) FROM customers",
            difficulty="easy",
        ),
        EvalItem(
            id="test-names",
            dataset="custom",
            db_id="test",
            sqlite_path=str(sample_sqlite_path),
            question="all customer names",
            gold_sql="SELECT name FROM customers",
            difficulty="easy",
        ),
    ]


async def test_runner_marks_correct_prediction(two_item_set):
    provider = ScriptedProvider(
        [
            tool_call_resp("execute_sql", {"sql": "SELECT COUNT(*) FROM customers"}),
            text_resp("done"),
        ]
    )
    outcomes = await run_items(two_item_set[:1], provider=provider)
    assert len(outcomes) == 1
    o = outcomes[0]
    assert o.correct is True
    assert o.predicted_sql == "SELECT COUNT(*) FROM customers"
    assert o.iterations_used == 2
    assert o.stop_reason == "answered"
    assert "execute_sql(sql=SELECT COUNT(*) FROM customers)" in o.tool_calls


async def test_runner_marks_wrong_prediction(two_item_set):
    # Question asks for count, model returns the ids instead — wrong row shape.
    provider = ScriptedProvider(
        [
            tool_call_resp("execute_sql", {"sql": "SELECT id FROM customers"}),
            text_resp("done"),
        ]
    )
    outcomes = await run_items(two_item_set[:1], provider=provider)
    assert outcomes[0].correct is False


async def test_runner_records_provider_failure_without_crashing(two_item_set):
    class Boom:
        async def chat(self, messages, tools=None, temperature=0.0):
            raise RuntimeError("nope")

    outcomes = await run_items(two_item_set[:1], provider=Boom())
    o = outcomes[0]
    assert o.correct is False
    assert o.stop_reason.startswith("provider_error")


async def test_runner_reuses_db_registration_across_items(two_item_set):
    # Two items on the same sqlite_path — should register only once.
    provider = ScriptedProvider(
        [
            tool_call_resp("execute_sql", {"sql": "SELECT COUNT(*) FROM customers"}),
            text_resp("a"),
            tool_call_resp("execute_sql", {"sql": "SELECT name FROM customers"}),
            text_resp("b"),
        ]
    )
    outcomes = await run_items(two_item_set, provider=provider)
    assert all(o.correct for o in outcomes)


async def test_runner_flags_broken_gold_sql(sample_sqlite_path: Path):
    bad_item = EvalItem(
        id="bad-gold",
        dataset="custom",
        db_id="test",
        sqlite_path=str(sample_sqlite_path),
        question="won't matter",
        gold_sql="SELECT * FROM no_such_table",
        difficulty="easy",
    )
    provider = ScriptedProvider([text_resp("noop")])
    outcomes = await run_items([bad_item], provider=provider)
    o = outcomes[0]
    assert o.correct is False
    assert o.stop_reason == "gold_sql_error"
    assert o.error is not None


async def test_summarize_computes_accuracy_and_difficulty_breakdown(two_item_set):
    provider = ScriptedProvider(
        [
            tool_call_resp("execute_sql", {"sql": "SELECT COUNT(*) FROM customers"}),
            text_resp("a"),
            tool_call_resp("execute_sql", {"sql": "SELECT id FROM customers"}),  # wrong
            text_resp("b"),
        ]
    )
    outcomes = await run_items(two_item_set, provider=provider)
    summary = summarize(outcomes, dataset="test", model="scripted")
    assert summary.total == 2
    assert summary.correct == 1
    assert summary.accuracy == 0.5
    assert summary.by_difficulty["easy"]["total"] == 2
    assert summary.by_difficulty["easy"]["correct"] == 1


# ---------- custom items smoke ----------


def test_custom_items_load_and_have_stable_ids():
    items = load_custom()
    assert len(items) >= 10
    ids = [it.id for it in items]
    assert len(ids) == len(set(ids)), "custom_items.json has duplicate ids"
    assert all(it.question and it.gold_sql for it in items)
