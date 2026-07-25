"""EvalItem model and dataset loaders.

Custom items live in `custom_items.json` next to this module. BIRD items are
fetched by `scripts/fetch_bird_subset.py` into `bird_data/subset.json`.

We deliberately do NOT thread BIRD's `evidence` field into the agent prompt.
The whole point of the agentic loop + schema RAG is that the model figures
things out from the schema; injecting curated hints would inflate the
baseline and make v3/v4 comparisons dishonest.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVAL_DIR.parent
REPO_DIR = BACKEND_DIR.parent


@dataclass
class EvalItem:
    id: str
    dataset: str  # "custom" | "bird"
    db_id: str  # logical name, e.g. "ecommerce" or BIRD's db_id
    sqlite_path: str  # resolved absolute path to the .sqlite file
    question: str
    gold_sql: str
    difficulty: str = "unknown"  # "easy" | "medium" | "hard" | "challenging" | ...
    evidence: str | None = None  # captured but not fed to the model
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def load_custom(limit: int | None = None) -> list[EvalItem]:
    """Load the hand-crafted eval set on ecommerce.sqlite."""
    items_path = EVAL_DIR / "custom_items.json"
    sqlite_path = REPO_DIR / "data" / "sample_dbs" / "ecommerce.sqlite"
    if not sqlite_path.exists():
        raise FileNotFoundError(
            f"Custom eval DB missing at {sqlite_path}. "
            "Re-create it (see CLAUDE.md 'Sample SQLite for demos')."
        )

    raw = json.loads(items_path.read_text(encoding="utf-8"))
    items = [
        EvalItem(
            id=r["id"],
            dataset="custom",
            db_id="ecommerce",
            sqlite_path=str(sqlite_path),
            question=r["question"],
            gold_sql=r["gold_sql"],
            difficulty=r.get("difficulty", "unknown"),
            evidence=r.get("evidence"),
            tags=r.get("tags", []),
        )
        for r in raw
    ]
    return items[:limit] if limit else items


def load_bird(limit: int | None = None) -> list[EvalItem]:
    """Load the BIRD subset. Runs `scripts/fetch_bird_subset.py` first if missing."""
    subset_path = EVAL_DIR / "bird_data" / "subset.json"
    if not subset_path.exists():
        raise FileNotFoundError(
            f"BIRD subset not found at {subset_path}. "
            "Run: python scripts/fetch_bird_subset.py"
        )
    raw = json.loads(subset_path.read_text(encoding="utf-8"))
    items = [
        EvalItem(
            id=r["id"],
            dataset="bird",
            db_id=r["db_id"],
            sqlite_path=r["sqlite_path"],  # already resolved by the fetcher
            question=r["question"],
            gold_sql=r["gold_sql"],
            difficulty=r.get("difficulty", "unknown"),
            evidence=r.get("evidence"),
            tags=r.get("tags", []),
        )
        for r in raw
    ]
    return items[:limit] if limit else items


def load_items(dataset: str, limit: int | None = None) -> list[EvalItem]:
    if dataset == "custom":
        return load_custom(limit=limit)
    if dataset == "bird":
        return load_bird(limit=limit)
    raise ValueError(f"Unknown dataset: {dataset!r} (expected 'custom' or 'bird')")
