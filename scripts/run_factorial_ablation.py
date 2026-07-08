"""
D-04 — Fractional factorial ablation (8 runs × 4 binary factors).

Usage:
  python scripts/run_factorial_ablation.py --gold data/eval/answer_gold_independent.jsonl --limit 10
  python scripts/run_factorial_ablation.py --json-out data/eval/factorial_ablation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.eval.ablation_pipeline import (  # noqa: E402
    AblationPipeline,
    EvalRunMode,
    FRACTIONAL_FACTORIAL_CONFIGS,
    FusionConfig,
)
from app.eval.quality_metrics import QualityScores, average_scores  # noqa: E402
from scripts.run_quality_ablation import (  # noqa: E402
    _filter_cases_by_gold_source,
    _load_gold,
)


def run_factorial(
    *,
    gold_path: Path,
    configs: tuple[FusionConfig, ...],
    limit: int | None,
    eval_run_mode: EvalRunMode,
    gold_source: str | None,
    kg_snapshot: str | None,
) -> dict:
    cases = _filter_cases_by_gold_source(_load_gold(gold_path), gold_source)
    if limit is not None:
        cases = cases[: max(0, limit)]

    pipeline = AblationPipeline(eval_run_mode=eval_run_mode)
    per_config: dict[str, list[QualityScores]] = defaultdict(list)
    details: list[dict] = []

    try:
        for case in cases:
            case_id = str(case.get("id") or "")
            for config in configs:
                result = pipeline.run_case_with_config(case, config)
                key = config.factor_key()
                per_config[key].append(result.scores)
                row = result.as_dict()
                row["fusion_config"] = key
                details.append(row)
    finally:
        pipeline.close()

    summary = {
        key: average_scores(scores).as_dict() for key, scores in per_config.items()
    }
    report = {
        "n_cases": len(cases),
        "n_configs": len(configs),
        "eval_run_mode": eval_run_mode.value,
        "gold_file": str(gold_path),
        "summary_by_config": summary,
        "details": details,
        "run_started_at": datetime.now(timezone.utc).isoformat(),
    }
    if kg_snapshot:
        report["kg_snapshot"] = kg_snapshot
    if gold_source:
        report["gold_source_filter"] = gold_source
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="D-04 fractional factorial ablation")
    parser.add_argument(
        "--gold",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval" / "answer_gold_independent.jsonl",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--eval-mode", choices=["static", "generative"], default="static")
    parser.add_argument("--gold-source", choices=["all", "derived", "independent"], default=None)
    parser.add_argument("--kg-snapshot", type=str, default=None, help="B2c snapshot tag e.g. kg_v0_pre_enrich")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    eval_mode = EvalRunMode.GENERATIVE if args.eval_mode == "generative" else EvalRunMode.STATIC
    report = run_factorial(
        gold_path=args.gold,
        configs=FRACTIONAL_FACTORIAL_CONFIGS,
        limit=args.limit,
        eval_run_mode=eval_mode,
        gold_source=args.gold_source,
        kg_snapshot=args.kg_snapshot,
    )
    print(json.dumps(report["summary_by_config"], ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report: {args.json_out}")


if __name__ == "__main__":
    main()
