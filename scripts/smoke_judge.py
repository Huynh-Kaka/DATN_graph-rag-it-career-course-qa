"""
D-03 — Smoke test LLM-as-Judge: xác nhận Judge trả JSON hợp lệ trước khi chạy eval đầy đủ.

Chạy:
  python scripts/smoke_judge.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.eval.llm_judge import create_judge_client, judge_model_label  # noqa: E402


def main() -> int:
    judge = create_judge_client()
    if not judge.available:
        print("FAIL: Judge client không khả dụng — kiểm tra JUDGE_PROVIDER và API key / CHATBOT_LOCAL_BASE_URL")
        return 1

    print(f"Smoke judge: {judge_model_label()}")

    try:
        scores = judge.score(
            question="Backend Developer cần học gì?",
            answer="Cần Python, SQL, API Design và Docker theo lộ trình graph.",
            ground_truth={
                "expected_careers": ["Backend Developer"],
                "expected_skills": ["Python", "SQL", "Docker"],
                "expected_courses": [],
                "eval_intent": "pathfinding",
            },
            graph_context={
                "career_name": "Backend Developer",
                "skills_missing": [{"name": "Python"}, {"name": "SQL"}],
            },
        )
    except Exception as exc:
        print(f"FAIL: Judge không trả JSON hợp lệ — {exc}")
        print("Gợi ý: kiểm tra proxy local, bật JSON mode, đổi JUDGE_LOCAL_MODEL")
        return 1

    if not (0.0 <= scores.faithfulness <= 1.0):
        print(f"FAIL: faithfulness ngoài [0,1]: {scores.faithfulness}")
        return 1
    if not (0.0 <= scores.skill_completeness <= 1.0):
        print(f"FAIL: skill_completeness ngoài [0,1]: {scores.skill_completeness}")
        return 1
    if not isinstance(scores.no_hallucination, bool):
        print(f"FAIL: no_hallucination không phải bool: {scores.no_hallucination!r}")
        return 1

    print(
        "PASS: Judge JSON OK — "
        f"faithfulness={scores.faithfulness:.2f}, "
        f"skill_completeness={scores.skill_completeness:.2f}, "
        f"no_hallucination={scores.no_hallucination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
