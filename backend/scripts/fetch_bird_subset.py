"""Fetch a small BIRD-SQL dev subset for eval.

BIRD hosts the dev split as a single zip on its OSS bucket. This script:
  1. Downloads dev.zip (if not already cached).
  2. Extracts it to backend/eval/bird_data/dev/.
  3. Samples N questions per configured DB with a fixed seed.
  4. Writes backend/eval/bird_data/subset.json — the file the eval runner reads.

Run once (or after changing the config below) — the fetched zip and databases
are gitignored.

Usage:
    cd backend
    python scripts/fetch_bird_subset.py
    python scripts/fetch_bird_subset.py --per-db 5   # smaller subset
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

# BIRD's official dev-set zip. Contains dev.json + dev_databases/<db>/<db>.sqlite.
BIRD_DEV_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"

# 3 well-known BIRD dev DBs with a range of schema complexity. Chosen to give
# the eval a portfolio-worthy spread without downloading the whole set for
# every developer. Change TARGET_DBS if you want different DBs represented.
TARGET_DBS = ["california_schools", "financial", "superhero"]
DEFAULT_PER_DB = 15
SAMPLE_SEED = 42

BACKEND_DIR = Path(__file__).resolve().parent.parent
BIRD_DIR = BACKEND_DIR / "eval" / "bird_data"
ZIP_PATH = BIRD_DIR / "dev.zip"
EXTRACT_ROOT = BIRD_DIR / "dev"
SUBSET_JSON = BIRD_DIR / "subset.json"


@dataclass
class BirdQuestion:
    """One raw entry from BIRD's dev.json."""

    question_id: int
    db_id: str
    question: str
    SQL: str
    difficulty: str | None = None
    evidence: str | None = None


def _download(url: str, dest: Path) -> None:
    """Streaming download with a live percentage — dev.zip is ~250 MB."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {url}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=None) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", "0"))
        got = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=1 << 20):
                f.write(chunk)
                got += len(chunk)
                if total:
                    pct = got * 100 / total
                    print(f"\r  {got // (1 << 20)} / {total // (1 << 20)} MiB ({pct:5.1f}%)", end="")
                else:
                    print(f"\r  {got // (1 << 20)} MiB", end="")
        print()
    tmp.replace(dest)


def _extract(zip_path: Path, target_dbs: list[str], out_root: Path) -> None:
    """Extract dev.json + the target DBs (not the whole 250 MB tree)."""
    out_root.mkdir(parents=True, exist_ok=True)
    keep_prefixes = tuple(f"dev_databases/{db}/" for db in target_dbs)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        # Some zips include a top-level "dev/" prefix, some don't. Detect it.
        top = ""
        if names and names[0].endswith("/") and names[0].count("/") == 1:
            top = names[0]
        for name in names:
            rel = name[len(top):] if top and name.startswith(top) else name
            if rel == "dev.json" or rel.startswith(keep_prefixes):
                dest = out_root / rel
                if name.endswith("/"):
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, dest.open("wb") as f:
                    f.write(src.read())
                print(f"  extracted {rel}")


def _load_questions(dev_json: Path) -> list[BirdQuestion]:
    raw = json.loads(dev_json.read_text(encoding="utf-8"))
    return [
        BirdQuestion(
            question_id=q["question_id"],
            db_id=q["db_id"],
            question=q["question"],
            SQL=q["SQL"],
            difficulty=q.get("difficulty"),
            evidence=q.get("evidence"),
        )
        for q in raw
    ]


def _build_subset(
    questions: list[BirdQuestion],
    target_dbs: list[str],
    per_db: int,
    seed: int,
    extract_root: Path,
) -> list[dict]:
    rng = random.Random(seed)
    subset: list[dict] = []
    for db_id in target_dbs:
        db_qs = [q for q in questions if q.db_id == db_id]
        if not db_qs:
            print(f"WARNING: no questions found for db {db_id!r}", file=sys.stderr)
            continue
        sampled = rng.sample(db_qs, k=min(per_db, len(db_qs)))
        sqlite_path = extract_root / "dev_databases" / db_id / f"{db_id}.sqlite"
        if not sqlite_path.exists():
            print(f"WARNING: sqlite missing for {db_id}: {sqlite_path}", file=sys.stderr)
            continue
        for q in sampled:
            subset.append(
                {
                    "id": f"bird-{db_id}-{q.question_id:04d}",
                    "db_id": db_id,
                    "sqlite_path": str(sqlite_path.resolve()),
                    "question": q.question,
                    "gold_sql": q.SQL,
                    "difficulty": (q.difficulty or "unknown").lower(),
                    "evidence": q.evidence,
                    "tags": ["bird", db_id],
                }
            )
    return subset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-db", type=int, default=DEFAULT_PER_DB)
    parser.add_argument("--seed", type=int, default=SAMPLE_SEED)
    parser.add_argument(
        "--dbs",
        default=",".join(TARGET_DBS),
        help="Comma-separated BIRD db_ids to sample from.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download dev.zip even if a cached copy exists.",
    )
    args = parser.parse_args()

    target_dbs = [d.strip() for d in args.dbs.split(",") if d.strip()]

    if args.force_download or not ZIP_PATH.exists():
        try:
            _download(BIRD_DEV_URL, ZIP_PATH)
        except httpx.HTTPError as e:
            print(f"\nDownload failed: {e}", file=sys.stderr)
            print(
                f"\nManual fallback: download {BIRD_DEV_URL} yourself, "
                f"drop it at {ZIP_PATH}, and rerun this script.",
                file=sys.stderr,
            )
            return 2
    else:
        print(f"using cached {ZIP_PATH}")

    _extract(ZIP_PATH, target_dbs, EXTRACT_ROOT)

    dev_json = EXTRACT_ROOT / "dev.json"
    if not dev_json.exists():
        print(f"ERROR: {dev_json} missing after extract", file=sys.stderr)
        return 3

    questions = _load_questions(dev_json)
    print(f"loaded {len(questions)} questions from dev.json")

    subset = _build_subset(questions, target_dbs, args.per_db, args.seed, EXTRACT_ROOT)
    if not subset:
        print("ERROR: subset is empty — nothing to write", file=sys.stderr)
        return 4

    SUBSET_JSON.write_text(json.dumps(subset, indent=2), encoding="utf-8")
    print(f"wrote {len(subset)} items to {SUBSET_JSON}")

    by_db: dict[str, int] = {}
    for it in subset:
        by_db[it["db_id"]] = by_db.get(it["db_id"], 0) + 1
    for db, n in sorted(by_db.items()):
        print(f"  {db:<24} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
