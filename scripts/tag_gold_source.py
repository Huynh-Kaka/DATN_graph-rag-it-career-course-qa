"""
Add gold_source metadata to eval gold JSONL files (non-destructive — only adds fields).

Usage:
  python scripts/tag_gold_source.py
  python scripts/tag_gold_source.py --file data/eval/answer_gold.jsonl --source derived_from_graph_repository
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_TARGETS: list[tuple[Path, str]] = [
    (PROJECT_ROOT / "data" / "eval" / "answer_gold.jsonl", "derived_from_graph_repository"),
    (PROJECT_ROOT / "data" / "eval" / "answer_gold_independent.jsonl", "excel_derived"),
]


def tag_file(path: Path, source: str, *, dry_run: bool = False, overwrite: bool = False) -> int:
    if not path.is_file():
        print(f"SKIP missing: {path}")
        return 0
    rows: list[dict] = []
    tagged = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if overwrite or not row.get("gold_source"):
                if row.get("gold_source") != source:
                    row["gold_source"] = source
                    tagged += 1
            rows.append(row)
    if dry_run:
        print(f"DRY RUN: would tag {tagged}/{len(rows)} in {path}")
        return tagged
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"OK: tagged {tagged}/{len(rows)} rows in {path}")
    return tagged


def main() -> None:
    parser = argparse.ArgumentParser(description="Add gold_source to eval JSONL gold files")
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument("--source", type=str, default="derived_from_graph_repository")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing gold_source values",
    )
    args = parser.parse_args()

    if args.file:
        tag_file(args.file, args.source, dry_run=args.dry_run, overwrite=args.overwrite)
        return

    for path, source in DEFAULT_TARGETS:
        overwrite = path.name == "answer_gold_independent.jsonl"
        tag_file(path, source, dry_run=args.dry_run, overwrite=overwrite)


if __name__ == "__main__":
    main()
