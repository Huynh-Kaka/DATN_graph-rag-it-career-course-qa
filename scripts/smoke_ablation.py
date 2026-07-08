"""
D-01 — Smoke test ablation: 1 case × 4 fusion modes (static), xác nhận Neo4j/Qdrant.

Chạy:
  python scripts/smoke_ablation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.eval.ablation_pipeline import AblationPipeline, EvalRunMode, FusionMode  # noqa: E402


def main() -> int:
    case = {
        "id": "smoke_pf_be",
        "intent": "pathfinding",
        "query": "Làm backend cần học gì?",
        "career": "Backend Developer",
        "gold_skills": ["Python", "SQL", "Docker"],
    }

    pipeline = AblationPipeline(eval_run_mode=EvalRunMode.STATIC)
    failures: list[str] = []
    try:
        for mode in FusionMode:
            result = pipeline.run_case(case, mode)
            row = result.as_dict()
            print(
                f"OK {mode.value}: faithfulness={row['scores']['faithfulness']:.3f} "
                f"skill_accuracy={row['scores']['skill_accuracy']:.3f} "
                f"graph_found={result.meta.get('graph_found')}"
            )
            if mode != FusionMode.VECTOR_ONLY and not result.meta.get("graph_found"):
                failures.append(f"{mode.value}: graph_found=false")
            if row["scores"]["faithfulness"] < 0:
                failures.append(f"{mode.value}: invalid faithfulness")
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        pipeline.close()

    if failures:
        print("FAIL:")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("Smoke ablation passed (1 case × 4 modes, static).")

    rel_case = {
        "id": "smoke_rel_react",
        "intent": "competency_relation",
        "query": "React cần học gì trước?",
        "competency": "React",
        "gold_related_codes": ["L_JS"],
    }
    pipeline2 = AblationPipeline(eval_run_mode=EvalRunMode.STATIC)
    rel_failures: list[str] = []
    try:
        result = pipeline2.run_case(rel_case, FusionMode.GRAPH_ONLY)
        row = result.as_dict()
        reply = str(row.get("reply") or "")
        recall = float(row["scores"].get("relation_code_recall") or 0.0)
        coverage = str(result.meta.get("coverage") or "")
        print(
            f"OK rel graph_only: relation_recall={recall} "
            f"coverage={coverage}"
        )
        if coverage == "none":
            rel_failures.append("rel: coverage=none")
        if "L_JS" not in reply and recall < 1.0:
            rel_failures.append("rel: L_JS missing and relation_code_recall < 1.0")
        if recall < 1.0:
            rel_failures.append(f"rel: relation_code_recall={recall} < 1.0")
    except Exception as exc:
        print(f"FAIL rel smoke: {exc}")
        return 1
    finally:
        pipeline2.close()

    if rel_failures:
        print("FAIL rel assertions:")
        for msg in rel_failures:
            print(f"  - {msg}")
        return 1

    print("Smoke ablation passed (pathfinding + competency_relation).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
