"""Execution accuracy — the BIRD-standard text-to-SQL metric.

We compare the row-set returned by the predicted SQL to the row-set returned
by the gold SQL. If the gold contains ORDER BY, comparison is order-sensitive
(the user asked for an ordering, so ordering matters); otherwise it's a
multiset comparison (SQL doesn't guarantee row order without ORDER BY).

Column names and column order are ignored — this matches how BIRD's own
evaluator behaves. The model's freedom to alias columns shouldn't cost it
accuracy.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

import sqlglot
from sqlglot import expressions as exp

# Float rounding tolerance for cell comparison — enough digits to catch real
# arithmetic differences, loose enough to ignore last-bit float noise.
FLOAT_ROUND = 4


def has_order_by(sql: str) -> bool:
    """True iff the top-level statement (or its outermost SELECT) has ORDER BY."""
    try:
        parsed = sqlglot.parse_one(sql, read="sqlite")
    except Exception:  # noqa: BLE001 — malformed gold is a data bug, not a crash
        return False
    if parsed is None:
        return False
    # ORDER BY inside a subquery or CTE doesn't determine outer-result order.
    order = parsed.args.get("order") if isinstance(parsed, exp.Select) else None
    if order is not None:
        return True
    # WITH ... SELECT: the ORDER BY sits on the wrapped SELECT.
    if isinstance(parsed, exp.With):
        inner = parsed.this
        if isinstance(inner, exp.Select) and inner.args.get("order") is not None:
            return True
    # UNION/etc — check the outermost expression's order arg generically.
    return parsed.args.get("order") is not None


def _normalize_cell(value: Any) -> Any:
    """Cast a cell to something Counter-hashable and comparable across runs."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bools ARE ints in Python; keep them distinct from 1/0 for gold comparison
        return ("__bool__", value)
    if isinstance(value, float):
        return round(value, FLOAT_ROUND)
    if isinstance(value, int):
        # Compare 3 and 3.0 as equal.
        return round(float(value), FLOAT_ROUND) if _looks_like_amount(value) else value
    if isinstance(value, (list, tuple)):
        return tuple(_normalize_cell(v) for v in value)
    return value


def _looks_like_amount(_: int) -> bool:
    # Placeholder: we treat all ints as-is. Kept as its own function so
    # future policy tweaks (e.g. cast numerics uniformly) have one place.
    return False


def _normalize_row(row: Iterable[Any]) -> tuple:
    return tuple(_normalize_cell(v) for v in row)


def rows_equal_unordered(a: list[list[Any]], b: list[list[Any]]) -> bool:
    return Counter(_normalize_row(r) for r in a) == Counter(_normalize_row(r) for r in b)


def rows_equal_ordered(a: list[list[Any]], b: list[list[Any]]) -> bool:
    if len(a) != len(b):
        return False
    return all(_normalize_row(x) == _normalize_row(y) for x, y in zip(a, b, strict=True))


def execution_accuracy(
    pred_rows: list[list[Any]] | None,
    gold_rows: list[list[Any]] | None,
    *,
    gold_sql: str,
) -> bool:
    """True iff the predicted result matches the gold result under BIRD-style semantics."""
    if pred_rows is None or gold_rows is None:
        return False
    if has_order_by(gold_sql):
        return rows_equal_ordered(pred_rows, gold_rows)
    return rows_equal_unordered(pred_rows, gold_rows)
