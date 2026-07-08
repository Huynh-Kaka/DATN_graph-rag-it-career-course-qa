"""
Label retrieval gold queries as trivial vs paraphrased (D-12).

Usage:
  python scripts/analyze_gold_triviality.py
  python scripts/analyze_gold_triviality.py --write-labeled data/eval/retrieval_gold_labeled.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    from unidecode import unidecode
except ImportError:
    def unidecode(text: str) -> str:
        return text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLD = PROJECT_ROOT / "data" / "eval" / "retrieval_gold.jsonl"


def _norm(text: str) -> str:
    folded = unidecode(str(text or ""))
    return re.sub(r"\s+", " ", folded.strip().lower())


def gold_entity_strings(row: dict) -> list[str]:
    entities: list[str] = []
    for g in row.get("gold_ids") or []:
        if g:
            entities.append(str(g))
    comp = row.get("gold_competency")
    if comp:
        entities.append(str(comp))
    return entities


def classify_query_difficulty(row: dict) -> str:
    """trivial if query contains gold entity verbatim (case-insensitive)."""
    query = _norm(row.get("query") or "")
    if not query:
        return "unknown"
    for entity in gold_entity_strings(row):
        ent = _norm(entity)
        if len(ent) >= 2 and ent in query:
            return "trivial"
    return "paraphrased"


def label_rows(rows: list[dict]) -> list[dict]:
    labeled: list[dict] = []
    for row in rows:
        copy = dict(row)
        copy["query_difficulty"] = classify_query_difficulty(row)
        labeled.append(copy)
    return labeled


def summarize(rows: list[dict]) -> dict[str, Counter[str]]:
    by_doc: Counter[str] = Counter()
    by_diff: Counter[str] = Counter()
    cross: Counter[str] = Counter()
    for row in rows:
        doc_type = str(row.get("doc_type") or "unknown")
        diff = str(row.get("query_difficulty") or classify_query_difficulty(row))
        by_doc[doc_type] += 1
        by_diff[diff] += 1
        cross[f"{doc_type}:{diff}"] += 1
    return {"by_doc_type": by_doc, "by_difficulty": by_diff, "cross": cross}


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze trivial vs paraphrased retrieval gold")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--write-labeled", type=Path, default=None)
    args = parser.parse_args()

    rows: list[dict] = []
    with args.gold.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    labeled = label_rows(rows)
    stats = summarize(labeled)

    print(f"Analyzed {len(labeled)} queries from {args.gold}")
    print("By difficulty:", dict(stats["by_difficulty"]))
    print("Cross doc_type:difficulty (top):")
    for key, count in stats["cross"].most_common(12):
        print(f"  {key}: {count}")

    if args.write_labeled:
        args.write_labeled.parent.mkdir(parents=True, exist_ok=True)
        with args.write_labeled.open("w", encoding="utf-8") as f:
            for row in labeled:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote labeled gold -> {args.write_labeled}")


if __name__ == "__main__":
    main()
