"""
Latency benchmark for graph intents (thesis SLA demo).

Chạy:
  python scripts/benchmark_latency.py
  python scripts/benchmark_latency.py --out results/latency_baseline.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.eval.ablation_pipeline import AblationPipeline, EvalRunMode, FusionMode  # noqa: E402

_QUERIES = {
    "pathfinding": [
        {"query": "Backend Developer cần học gì?", "career": "Backend Developer", "intent": "pathfinding"},
        {"query": "Frontend roadmap", "career": "Frontend Developer", "intent": "pathfinding"},
    ],
    "course_rec": [
        {"query": "Khóa Python beginner", "competency": "Python", "intent": "course_rec"},
        {"query": "Khóa React", "competency": "React", "intent": "course_rec"},
    ],
    "competency_relation": [
        {"query": "React cần học gì trước?", "competency": "React", "intent": "competency_relation"},
        {"query": "CKA validate gì?", "competency": "CKA", "intent": "competency_relation"},
    ],
}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((pct / 100) * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "results" / "latency_baseline.json")
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args()

    pipeline = AblationPipeline(eval_run_mode=EvalRunMode.STATIC)
    report: dict[str, dict] = {}

    try:
        for intent, cases in _QUERIES.items():
            latencies: list[float] = []
            for case in cases:
                for _ in range(args.repeats):
                    t0 = time.perf_counter()
                    pipeline.run_case(case, FusionMode.GRAPH_ONLY)
                    latencies.append(time.perf_counter() - t0)
            report[intent] = {
                "n_runs": len(latencies),
                "n": len(latencies),
                "repeats_per_query": args.repeats,
                "n_queries": len(cases),
                "mean_ms": round(statistics.mean(latencies) * 1000, 2),
                "p95_ms": round(_percentile(latencies, 95) * 1000, 2),
                "max_ms": round(max(latencies) * 1000, 2),
            }
    finally:
        pipeline.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
