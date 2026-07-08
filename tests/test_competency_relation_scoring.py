"""G2 — scoring router for competency_relation."""

from __future__ import annotations

import json
from pathlib import Path

from app.intent.competency_relation_detect import (
    comparison_pattern,
    has_relation_signal,
    score_competency_relation_route,
    score_course_rec_affinity,
    should_route_competency_relation,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANSWER_GOLD = PROJECT_ROOT / "data" / "eval" / "answer_gold.jsonl"
ANSWER_GOLD_REL = PROJECT_ROOT / "data" / "eval" / "answer_gold_rel.jsonl"


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def test_has_relation_signal_prerequisite():
    assert has_relation_signal("React cần học gì trước khi bắt đầu?")


def test_has_relation_signal_cert():
    assert has_relation_signal("Chứng chỉ nào validate AWS platform?")


def test_comparison_pattern():
    assert comparison_pattern("Học JavaScript hay TypeScript trước?")


def test_score_hybrid_career_and_relation():
    q = "Data Scientist cần học Python hay SQL trước?"
    score = score_competency_relation_route(q)
    assert score >= 3.0
    assert should_route_competency_relation(q)


def test_score_career_only_penalized_without_relation():
    q = "Lộ trình Backend Developer cần học những gì?"
    score = score_competency_relation_route(q)
    assert score < 3.0
    assert not should_route_competency_relation(q)


def test_score_pure_relation_single_competency():
    q = "Muốn học Django thì cần biết ngôn ngữ nào?"
    assert should_route_competency_relation(q)


def test_course_rec_corpus_should_not_route_relation():
    if not ANSWER_GOLD.is_file():
        return
    course_queries = [
        r["query"] for r in _load_jsonl(ANSWER_GOLD) if r.get("intent") == "course_rec"
    ]
    assert len(course_queries) >= 5
    for q in course_queries:
        assert not should_route_competency_relation(q), q


def test_relation_corpus_should_route_relation():
    if not ANSWER_GOLD_REL.is_file():
        return
    rel_queries = [
        r["query"] for r in _load_jsonl(ANSWER_GOLD_REL) if r.get("intent") == "competency_relation"
    ][:8]
    assert len(rel_queries) >= 5
    routed = sum(1 for q in rel_queries if should_route_competency_relation(q))
    assert routed >= 4


def test_cr_react_fastapi_not_relation():
    assert not should_route_competency_relation("Gợi ý khóa học React beginner")
    assert not should_route_competency_relation("Học FastAPI cho Python")
