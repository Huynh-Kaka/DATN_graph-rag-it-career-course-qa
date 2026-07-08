"""
Summarize E2E eval + optional attribution vs baseline.

Usage:
  python scripts/summarize_eval_results.py
  python scripts/summarize_eval_results.py --baseline results/baseline_pre_router_v22.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CSV = PROJECT_ROOT / "data" / "eval" / "answer_quality_results.csv"
DEFAULT_OUT = PROJECT_ROOT / "results" / "verification_summary_v22.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rates_from_csv(path: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    total = len(rows)
    if total == 0:
        return {"total": 0, "valid_n": 0, "valid_rate": 0.0}
    valid = sum(1 for r in rows if r.get("run_status") == "valid_run")
    route_mm = sum(1 for r in rows if r.get("run_status") == "route_mismatch")
    infra = sum(1 for r in rows if r.get("run_status") == "infra_error")
    faith_vals = [float(r["faithfulness"]) for r in rows if r.get("run_status") == "valid_run"]
    return {
        "total": total,
        "valid_n": valid,
        "valid_rate": valid / total,
        "route_mismatch_n": route_mm,
        "infra_error_n": infra,
        "faithfulness": sum(faith_vals) / len(faith_vals) if faith_vals else 0.0,
    }


def _delta(post: float, base: float) -> float:
    return round(post - base, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize verification results")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if args.report_json and args.report_json.is_file():
        current = _load_json(args.report_json)
    elif args.csv.is_file():
        current = {"overall": _rates_from_csv(args.csv)}
    else:
        print(f"ERROR: missing {args.csv}")
        raise SystemExit(1)

    summary: dict[str, Any] = {"current": current}
    if args.baseline and args.baseline.is_file():
        baseline = _load_json(args.baseline)
        b_cohort = (baseline.get("by_cohort") or {}).get("v21_legacy") or baseline.get("overall") or {}
        c_cohort = (current.get("by_cohort") or {}).get("v21_legacy") or current.get("overall") or {}
        summary["attribution_v21_38"] = {
            "baseline_valid_rate": b_cohort.get("valid_n", 0) / max(b_cohort.get("total", 1), 1),
            "current_valid_rate": c_cohort.get("valid_n", 0) / max(c_cohort.get("total", 1), 1),
            "delta_valid_rate": _delta(
                c_cohort.get("valid_n", 0) / max(c_cohort.get("total", 1), 1),
                b_cohort.get("valid_n", 0) / max(b_cohort.get("total", 1), 1),
            ),
            "delta_route_mismatch": _delta(
                float(c_cohort.get("route_mismatch_n", 0)),
                float(b_cohort.get("route_mismatch_n", 0)),
            ),
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()
