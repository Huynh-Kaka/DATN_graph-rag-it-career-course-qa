"""
Compute regression delta threshold from pilot ablation runs (2×std).

Usage:
  python scripts/compute_regression_threshold.py \
    --inputs results/pilot_var_1.json results/pilot_var_2.json results/pilot_var_3.json \
    --out results/regression_variance_v2.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

DEFAULT_METRICS = ("answer_entity_f1", "exclusive_graph_rate", "ontology_f1")


def _load_summary(path: Path) -> dict[str, dict[str, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary") or {}
    out: dict[str, dict[str, float]] = {}
    for mode_label, scores in summary.items():
        if not isinstance(scores, dict):
            continue
        out[mode_label] = {
            k: float(v)
            for k, v in scores.items()
            if isinstance(v, (int, float)) and k in DEFAULT_METRICS
        }
    return out


def compute_thresholds(
    inputs: list[Path],
    *,
    metrics: tuple[str, ...] = DEFAULT_METRICS,
    floor: float = 0.02,
) -> dict[str, Any]:
    runs: list[dict[str, dict[str, float]]] = [_load_summary(p) for p in inputs]
    modes = sorted({m for run in runs for m in run.keys()})
    thresholds: dict[str, dict[str, float]] = {}

    for mode in modes:
        thresholds[mode] = {}
        for metric in metrics:
            vals = [run[mode][metric] for run in runs if metric in run.get(mode, {})]
            if len(vals) < 2:
                thresholds[mode][metric] = floor
                continue
            mean = sum(vals) / len(vals)
            var = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
            std = math.sqrt(var)
            thresholds[mode][metric] = round(max(floor, 2 * std), 4)

    return {
        "n_runs": len(inputs),
        "metrics": list(metrics),
        "floor": floor,
        "thresholds": thresholds,
        "input_files": [str(p) for p in inputs],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--floor", type=float, default=0.02)
    args = parser.parse_args()

    for p in args.inputs:
        if not p.is_file():
            print(f"ERROR: missing {p}")
            sys.exit(1)

    result = compute_thresholds(args.inputs, floor=args.floor)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
