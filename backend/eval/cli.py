"""Eval CLI.

Usage:
    cd backend
    python -m eval.cli --set custom
    python -m eval.cli --set custom --limit 5 --out results/quick.json
    python -m eval.cli --set bird --limit 10

Writes {outcomes, summary} JSON to --out (default: eval/results/<set>-<ts>.json).
Streams a compact per-item status line to stdout as it runs.

Real-model runs need NVIDIA_API_KEY in backend/.env.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.agent.provider import LLMProvider, NemotronProvider
from app.config import settings

from .datasets import EVAL_DIR, load_items
from .runner import EvalOutcome, run_items, summarize


def _build_provider(model: str) -> LLMProvider:
    if not settings.nvidia_api_key:
        raise SystemExit(
            "NVIDIA_API_KEY is not set. Add it to backend/.env before running the eval."
        )
    return NemotronProvider(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        model=model,
    )


def _default_out(dataset: str) -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return EVAL_DIR / "results" / f"{dataset}-{ts}.json"


def _print_progress(idx: int, total: int, o: EvalOutcome) -> None:
    mark = "PASS" if o.correct else "FAIL"
    tail = f" [{o.stop_reason}]" if not o.correct else ""
    print(
        f"  [{idx:>3}/{total}] {mark} {o.difficulty:<10} {o.item_id:<22} "
        f"iter={o.iterations_used} {o.elapsed_s:5.1f}s{tail}",
        flush=True,
    )


def _print_summary(summary) -> None:
    print("-" * 72)
    print(
        f"{summary.dataset}: {summary.correct}/{summary.total} correct "
        f"({summary.accuracy:.1%})   model={summary.model}   "
        f"avg_iter={summary.avg_iterations:.2f}"
    )
    for diff, b in sorted(summary.by_difficulty.items()):
        print(f"  {diff:<12} {b['correct']:>2}/{b['total']:<2}  ({b['accuracy']:.0%})")


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="eval.cli")
    parser.add_argument("--set", dest="dataset", choices=["custom", "bird"], required=True)
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of items.")
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=settings.max_agent_iterations,
        help="Max agent iterations per item (default from settings).",
    )
    parser.add_argument(
        "--model",
        default=settings.default_model,
        help="Model id (default from settings).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: eval/results/<set>-<ts>.json).",
    )
    args = parser.parse_args(argv)

    items = load_items(args.dataset, limit=args.limit)
    if not items:
        print(f"No items in dataset {args.dataset!r}.", file=sys.stderr)
        return 2

    provider = _build_provider(args.model)

    print(f"dataset : {args.dataset}   items={len(items)}   model={args.model}")
    print(f"max_iter: {args.max_iterations}")
    print("-" * 72)

    outcomes = await run_items(
        items,
        provider=provider,
        max_iterations=args.max_iterations,
        on_item=_print_progress,
    )
    summary = summarize(outcomes, dataset=args.dataset, model=args.model)
    _print_summary(summary)

    out_path = args.out or _default_out(args.dataset)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "summary": summary.to_dict(),
                "outcomes": [o.to_dict() for o in outcomes],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out_path}")
    return 0 if summary.accuracy > 0 else 1


def main() -> None:
    try:
        sys.exit(asyncio.run(_main(sys.argv[1:])))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
