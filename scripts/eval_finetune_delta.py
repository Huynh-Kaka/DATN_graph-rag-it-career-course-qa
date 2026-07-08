"""
D-08 — Compare answer quality before/after fine-tune on the same gold set.

Usage:
  python scripts/eval_finetune_delta.py --gold data/eval/answer_gold_independent.jsonl --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.eval.ablation_pipeline import AblationPipeline, EvalRunMode, FusionMode  # noqa: E402
from app.eval.quality_metrics import QualityScores  # noqa: E402
from app.eval.statistics import compare_groups_effect, summarize_with_ci  # noqa: E402
from scripts.run_quality_ablation import _filter_cases_by_gold_source, _load_gold  # noqa: E402


def _run_gold(
    cases: list[dict],
    *,
    eval_run_mode: EvalRunMode,
    mode: FusionMode,
) -> list[QualityScores]:
    pipeline = AblationPipeline(eval_run_mode=eval_run_mode)
    scores: list[QualityScores] = []
    try:
        for case in cases:
            result = pipeline.run_case(case, mode)
            scores.append(result.scores)
    finally:
        pipeline.close()
    return scores


def _metric_values(scores: list[QualityScores], metric: str) -> list[float]:
    out: list[float] = []
    for s in scores:
        data = s.as_dict()
        val = data.get(metric)
        if val is not None:
            out.append(float(val))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="D-08 fine-tune delta eval (static proxy)")
    parser.add_argument(
        "--gold",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval" / "answer_gold_independent.jsonl",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--eval-mode", choices=["static", "generative"], default="static")
    parser.add_argument("--gold-source", choices=["all", "derived", "independent"], default="independent")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    cases = _filter_cases_by_gold_source(_load_gold(args.gold), args.gold_source)
    if args.limit is not None:
        cases = cases[: max(0, args.limit)]

    eval_mode = EvalRunMode.GENERATIVE if args.eval_mode == "generative" else EvalRunMode.STATIC

    # Proxy "before": vector_only baseline; "after": tight_fusion (domain-tuned stack proxy).
    before = _run_gold(cases, eval_run_mode=eval_mode, mode=FusionMode.VECTOR_ONLY)
    after = _run_gold(cases, eval_run_mode=eval_mode, mode=FusionMode.TIGHT_FUSION)

    metric = "answer_entity_f1" if eval_mode == EvalRunMode.STATIC else "faithfulness"
    before_vals = _metric_values(before, metric)
    after_vals = _metric_values(after, metric)

    report = {
        "n_cases": len(cases),
        "metric": metric,
        "before_vector_only": summarize_with_ci(before_vals, label="before"),
        "after_tight_fusion": summarize_with_ci(after_vals, label="after"),
        "effect": compare_groups_effect(before_vals, after_vals),
        "note": (
            "Proxy delta: vector_only vs tight_fusion on same gold. "
            "Replace with actual base vs fine-tuned LLM when Ollama checkpoint is wired."
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
