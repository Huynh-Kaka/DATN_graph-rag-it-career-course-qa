"""
Compare two ablation JSON reports (baseline vs candidate).

Usage:
  python scripts/compare_ablation_runs.py \
    --baseline results/ablation_d01_v2_static.json \
    --candidate results/ablation_d01_v2_static_post_cr_guard25.json \
    --filter-baseline-to-candidate \
    --out results/ablation_regression_delta_post_cr.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_METRICS = (
    "answer_entity_f1",
    "exclusive_graph_rate",
    "ontology_f1",
    "relation_code_recall",
)


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _detail_index(details: list[dict]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for row in details:
        cid = str(row.get("case_id") or "")
        mode = str(row.get("mode") or "")
        if cid and mode:
            out[(cid, mode)] = row
    return out


def _candidate_case_ids(details: list[dict]) -> set[str]:
    return {str(r.get("case_id") or "") for r in details if r.get("case_id")}


def _filter_details(details: list[dict], case_ids: set[str]) -> list[dict]:
    return [r for r in details if str(r.get("case_id") or "") in case_ids]


def _metric_val(row: dict, metric: str) -> float | None:
    scores = row.get("scores") or {}
    val = scores.get(metric)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    metrics: list[str],
    filter_baseline_to_candidate: bool,
    regression_f1_drop: float = 0.15,
) -> dict[str, Any]:
    b_details = list(baseline.get("details") or [])
    c_details = list(candidate.get("details") or [])

    if filter_baseline_to_candidate:
        ids = _candidate_case_ids(c_details)
        b_details = _filter_details(b_details, ids)

    b_idx = _detail_index(b_details)
    c_idx = _detail_index(c_details)

    paired_keys = sorted(set(b_idx.keys()) & set(c_idx.keys()))
    per_pair: list[dict[str, Any]] = []
    by_mode_metric: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    regressions: list[dict[str, Any]] = []

    for key in paired_keys:
        cid, mode = key
        brow = b_idx[key]
        crow = c_idx[key]
        deltas: dict[str, float | None] = {}
        for metric in metrics:
            bval = _metric_val(brow, metric)
            cval = _metric_val(crow, metric)
            if bval is not None and cval is not None:
                delta = cval - bval
                deltas[metric] = round(delta, 4)
                by_mode_metric[mode][metric].append(delta)
                if metric == "answer_entity_f1" and delta < -regression_f1_drop:
                    regressions.append(
                        {
                            "case_id": cid,
                            "mode": mode,
                            "baseline": bval,
                            "candidate": cval,
                            "delta": delta,
                        }
                    )
        per_pair.append({"case_id": cid, "mode": mode, "deltas": deltas})

    summary_by_mode: dict[str, dict[str, float | None]] = {}
    for mode, metric_map in by_mode_metric.items():
        summary_by_mode[mode] = {}
        for metric, deltas in metric_map.items():
            summary_by_mode[mode][metric] = (
                round(sum(deltas) / len(deltas), 4) if deltas else None
            )

    return {
        "baseline_file": baseline.get("gold_file"),
        "candidate_file": candidate.get("gold_file"),
        "n_paired": len(paired_keys),
        "n_regressions_f1_drop": len(regressions),
        "regressions": regressions,
        "summary_delta_by_mode": summary_by_mode,
        "paired_details": per_pair,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare ablation JSON runs")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--metrics",
        type=str,
        default=",".join(DEFAULT_METRICS),
    )
    parser.add_argument(
        "--filter-baseline-to-candidate",
        action="store_true",
        help="Keep only baseline rows whose case_id appears in candidate",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--regression-f1-drop",
        type=float,
        default=0.15,
    )
    args = parser.parse_args()

    if not args.baseline.is_file() or not args.candidate.is_file():
        print("ERROR: baseline or candidate file missing")
        sys.exit(1)

    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]
    result = compare_reports(
        _load_report(args.baseline),
        _load_report(args.candidate),
        metrics=metrics,
        filter_baseline_to_candidate=args.filter_baseline_to_candidate,
        regression_f1_drop=args.regression_f1_drop,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary_delta_by_mode"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.out} (paired={result['n_paired']}, regressions={result['n_regressions_f1_drop']})")


if __name__ == "__main__":
    main()
