"""
Evaluate retrieval quality on retrieval_gold.jsonl (D-02).

Metrics: Recall@k, Precision@k, MRR, nDCG@k — overall và theo doc_type.

Chạy:
  python scripts/eval_retrieval.py
  python scripts/eval_retrieval.py --k 5,10 --doc-type career
  python scripts/eval_retrieval.py --k 5 --limit 20 --verbose
"""

from __future__ import annotations

import os

os.environ["RETRIEVAL_STRICT"] = "1"

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)
os.environ["RETRIEVAL_STRICT"] = "1"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.core import config as _config

os.environ["RETRIEVAL_STRICT"] = "1"
_config.settings = _config.Settings()

from app.eval.retrieval_metrics import RetrievalMetricRow, aggregate_query_metrics
from scripts.analyze_gold_triviality import classify_query_difficulty
from app.rag.retriever import VectorRetriever

_GOLD = PROJECT_ROOT / "data" / "eval" / "retrieval_gold.jsonl"
_DEFAULT_CSV = PROJECT_ROOT / "data" / "eval" / "retrieval_results.csv"


def _load_gold(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _parse_tag_list(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {t.strip() for t in raw.split(",") if t.strip()}


def _filter_gold_by_tags(
    gold: list[dict],
    *,
    filter_tags: set[str],
    exclude_tags: set[str],
) -> list[dict]:
    out: list[dict] = []
    for row in gold:
        tags = set(row.get("tags") or [])
        if filter_tags and not filter_tags.issubset(tags):
            continue
        if exclude_tags and tags & exclude_tags:
            continue
        out.append(row)
    return out


def _has_gold(row: dict) -> bool:
    gold_ids = row.get("gold_ids") or []
    if gold_ids:
        return True
    comp = (row.get("gold_competency") or "").strip()
    return bool(comp)


def _hit(doc: dict, row: dict) -> bool:
    payload = doc.payload
    field = row.get("gold_field") or "career_name"
    gold_ids = set(row.get("gold_ids") or [])

    if field == "career_name":
        title = str(payload.get("career_name") or payload.get("title") or "")
        text = str(payload.get("text") or "")
        for g in gold_ids:
            if g and (g in title or title == g or g.lower() in text.lower()):
                return True
        return False

    if field == "competency":
        comp = row.get("gold_competency") or ""
        text = (payload.get("text") or "") + " " + str(payload.get("title") or "")
        item_name = str(payload.get("item_name") or "")
        if comp.lower() in text.lower() or comp.lower() == item_name.lower():
            return True
        comps = payload.get("competencies") or []
        return any(comp.lower() in str(c).lower() for c in comps)

    if field == "item_code":
        gold_ids = {str(g) for g in gold_ids if g}
        item_code = str(payload.get("item_code") or payload.get("canonical_id") or "")
        related = str(payload.get("related_code") or "")
        if item_code in gold_ids or related in gold_ids:
            return True
        text = str(payload.get("text") or "") + " " + str(payload.get("title") or "")
        return any(g and g.lower() in text.lower() for g in gold_ids)

    canonical = str(payload.get("canonical_id") or "")
    related = str(payload.get("related_code") or "")
    return canonical in gold_ids or related in gold_ids


def _relevance_vector(docs: list, row: dict, *, max_k: int) -> list[int]:
    rels = [1 if _hit(d, row) else 0 for d in docs[:max_k]]
    if len(rels) < max_k:
        rels.extend([0] * (max_k - len(rels)))
    return rels


def _parse_k_values(raw: str) -> list[int]:
    out: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        k = int(part)
        if k <= 0:
            raise ValueError(f"k must be positive, got {k}")
        out.append(k)
    if not out:
        raise ValueError("At least one k value is required")
    return sorted(set(out))


def _n_relevant_total(row: dict) -> int:
    """Count relevant documents for full Recall@k (may exceed 1)."""
    field = row.get("gold_field") or "career_name"
    gold_ids = [g for g in (row.get("gold_ids") or []) if g]
    if field == "competency":
        return 1 if (row.get("gold_competency") or "").strip() else max(len(gold_ids), 1)
    if gold_ids:
        return len(gold_ids)
    comp = (row.get("gold_competency") or "").strip()
    return 1 if comp else 0


def _evaluate(
    gold: list[dict],
    retriever: VectorRetriever,
    *,
    k_values: list[int],
    verbose: bool,
) -> tuple[dict[str, list[list[int]]], dict[str, list[int]]]:
    """Chạy retriever; trả về relevance vectors và n_relevant totals theo nhóm."""
    max_k = max(k_values)
    grouped: dict[str, list[list[int]]] = defaultdict(list)
    grouped_n_rel: dict[str, list[int]] = defaultdict(list)

    for row in gold:
        if not _has_gold(row):
            if verbose:
                print(f"SKIP (no gold): {row.get('query')!r}")
            continue

        q = row["query"]
        doc_type = row.get("doc_type") or "unknown"
        docs = retriever.retrieve_docs(q, top_k=max_k, doc_type=doc_type)
        rels = _relevance_vector(docs, row, max_k=max_k)
        n_rel = _n_relevant_total(row)

        grouped["overall"].append(rels)
        grouped_n_rel["overall"].append(n_rel)
        grouped[doc_type].append(rels)
        grouped_n_rel[doc_type].append(n_rel)
        difficulty = str(row.get("query_difficulty") or classify_query_difficulty(row))
        grouped[f"difficulty:{difficulty}"].append(rels)
        grouped_n_rel[f"difficulty:{difficulty}"].append(n_rel)

        if verbose and not any(rels[: max(k_values)]):
            preview = [d.payload.get("title") for d in docs[:3]]
            print(f"MISS: {q!r} [{doc_type}] -> {preview}")

    return grouped, grouped_n_rel


def _build_metric_rows(
    grouped: dict[str, list[list[int]]],
    grouped_n_rel: dict[str, list[int]],
    k_values: list[int],
) -> list[RetrievalMetricRow]:
    rows: list[RetrievalMetricRow] = []
    doc_types = sorted(k for k in grouped if k != "overall" and not k.startswith("difficulty:"))
    difficulties = sorted(
        k.replace("difficulty:", "")
        for k in grouped
        if k.startswith("difficulty:")
    )

    for k in k_values:
        overall_rels = grouped.get("overall") or []
        overall_n_rel = grouped_n_rel.get("overall") or []
        hit_rate, precision, mrr, ndcg, recall_full, map_score = aggregate_query_metrics(
            overall_rels, k, n_relevant_totals=overall_n_rel or None
        )
        rows.append(
            RetrievalMetricRow(
                scope="overall",
                doc_type="all",
                k=k,
                n_queries=len(overall_rels),
                recall=hit_rate,
                precision=precision,
                mrr=mrr,
                ndcg=ndcg,
                hit_rate=hit_rate,
                recall_full=recall_full,
                map_score=map_score,
            )
        )

        for doc_type in doc_types:
            rels = grouped.get(doc_type) or []
            n_rel = grouped_n_rel.get(doc_type) or []
            hit_rate, precision, mrr, ndcg, recall_full, map_score = aggregate_query_metrics(
                rels, k, n_relevant_totals=n_rel or None
            )
            rows.append(
                RetrievalMetricRow(
                    scope="by_doc_type",
                    doc_type=doc_type,
                    k=k,
                    n_queries=len(rels),
                    recall=hit_rate,
                    precision=precision,
                    mrr=mrr,
                    ndcg=ndcg,
                    hit_rate=hit_rate,
                    recall_full=recall_full,
                    map_score=map_score,
                )
            )

        for difficulty in difficulties:
            rels = grouped.get(f"difficulty:{difficulty}") or []
            n_rel = grouped_n_rel.get(f"difficulty:{difficulty}") or []
            if not rels:
                continue
            hit_rate, precision, mrr, ndcg, recall_full, map_score = aggregate_query_metrics(
                rels, k, n_relevant_totals=n_rel or None
            )
            rows.append(
                RetrievalMetricRow(
                    scope="by_query_difficulty",
                    doc_type=difficulty,
                    k=k,
                    n_queries=len(rels),
                    recall=hit_rate,
                    precision=precision,
                    mrr=mrr,
                    ndcg=ndcg,
                    hit_rate=hit_rate,
                    recall_full=recall_full,
                    map_score=map_score,
                )
            )

    return rows


def _format_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _markdown_table(rows: list[RetrievalMetricRow]) -> str:
    header = (
        "| Scope | doc_type | k | HitRate@k | RecallFull@k | MAP | Precision@k | MRR | nDCG@k | N |\n"
        "|-------|----------|---|-----------|--------------|-----|-------------|-----|--------|---|"
    )
    lines = [header]
    for r in rows:
        recall_full = r.recall_full if r.recall_full is not None else r.recall
        map_score = r.map_score if r.map_score is not None else 0.0
        hit = r.hit_rate if r.hit_rate is not None else r.recall
        lines.append(
            f"| {r.scope} | {r.doc_type} | {r.k} | "
            f"{_format_pct(hit)} | {_format_pct(recall_full)} | {map_score:.4f} | "
            f"{_format_pct(r.precision)} | {r.mrr:.4f} | {r.ndcg:.4f} | {r.n_queries} |"
        )
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[RetrievalMetricRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scope",
        "doc_type",
        "k",
        "n_queries",
        "hit_rate_at_k",
        "recall_full_at_k",
        "map",
        "recall_at_k",
        "precision_at_k",
        "mrr",
        "ndcg_at_k",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_dict())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval: Recall@k, Precision@k, MRR, nDCG@k (D-02)."
    )
    parser.add_argument(
        "--k",
        type=str,
        default="5,10",
        help="Comma-separated cutoffs, e.g. 5,10 (default: 5,10)",
    )
    parser.add_argument("--gold", type=Path, default=_GOLD)
    parser.add_argument(
        "--doc-type",
        type=str,
        default=None,
        help="Evaluate only this doc_type (e.g. career, course)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate first N gold rows only",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=_DEFAULT_CSV,
        help=f"CSV output path (default: {_DEFAULT_CSV})",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Skip writing CSV file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-query MISS lines",
    )
    parser.add_argument(
        "--filter-tags",
        type=str,
        default=None,
        help="Keep rows whose tags contain ALL listed tags (comma-separated)",
    )
    parser.add_argument(
        "--exclude-tags",
        type=str,
        default=None,
        help="Drop rows whose tags intersect listed tags (comma-separated)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON metrics report to this path",
    )
    args = parser.parse_args()

    if not args.gold.is_file():
        print(f"ERROR: missing {args.gold}")
        sys.exit(1)

    try:
        k_values = _parse_k_values(args.k)
    except ValueError as exc:
        print(f"ERROR: invalid --k: {exc}")
        sys.exit(1)

    gold = _load_gold(args.gold)
    gold = _filter_gold_by_tags(
        gold,
        filter_tags=_parse_tag_list(args.filter_tags),
        exclude_tags=_parse_tag_list(args.exclude_tags),
    )
    if args.doc_type:
        gold = [r for r in gold if (r.get("doc_type") or "") == args.doc_type]
    if args.limit is not None:
        gold = gold[: max(0, args.limit)]

    if not gold:
        print("ERROR: no gold rows to evaluate (check --doc-type / --limit).")
        sys.exit(1)

    retriever = VectorRetriever()
    retriever.reload_bm25_corpus()

    grouped, grouped_n_rel = _evaluate(gold, retriever, k_values=k_values, verbose=args.verbose)
    metric_rows = _build_metric_rows(grouped, grouped_n_rel, k_values)

    print(f"\n## Retrieval evaluation ({args.gold.name})\n")
    if args.doc_type:
        print(f"Filter: doc_type = `{args.doc_type}`")
    print(f"Queries evaluated: {len(grouped.get('overall', []))}")
    print(f"k values: {', '.join(str(k) for k in k_values)}\n")
    print(_markdown_table(metric_rows))

    if not args.no_csv:
        _write_csv(args.output_csv, metric_rows)
        print(f"\nCSV saved: {args.output_csv}")

    if args.out:
        payload = {
            "gold_file": str(args.gold),
            "filter_tags": sorted(_parse_tag_list(args.filter_tags)),
            "exclude_tags": sorted(_parse_tag_list(args.exclude_tags)),
            "k_values": k_values,
            "n_queries": len(grouped.get("overall", [])),
            "metrics": [r.as_csv_dict() for r in metric_rows],
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON saved: {args.out}")


if __name__ == "__main__":
    main()
