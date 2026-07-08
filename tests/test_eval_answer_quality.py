"""Tests helpers trong scripts/eval_answer_quality.py (D-03)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.session.store import SessionState
from scripts.eval_answer_quality import (
    EvalRow,
    RUN_STATUS_VALID,
    RUN_STATUS_ROUTE_MISMATCH,
    _cohort_for_case,
    _flatten_known_skills,
    _normalize_case,
    _seed_session,
    aggregate_by_cohort,
    acceptable_routes_for_gold_intent,
    route_acceptable,
)
from app.eval.llm_judge import JudgeScores


def test_normalize_case_d03_schema():
    raw = {
        "id": "pf_ds_01",
        "question": "Lộ trình Data Scientist?",
        "intent": "pathfinding",
        "expected_careers": ["Data Scientist"],
        "expected_skills": ["Python", "SQL"],
        "expected_courses": [],
    }
    case = _normalize_case(raw)
    assert case["question"] == raw["question"]
    assert case["expected_careers"] == ["Data Scientist"]
    assert case["expected_skills"] == ["Python", "SQL"]
    assert case["expected_intent"] == "pathfinding"


def test_normalize_case_expected_intent_override():
    raw = {
        "id": "sg_01",
        "question": "Gap?",
        "intent": "skills_gap",
        "expected_intent": "skills_gap",
        "expected_careers": ["MLE"],
        "expected_skills": [],
        "expected_courses": [],
    }
    case = _normalize_case(raw)
    assert case["expected_intent"] == "skills_gap"


def test_normalize_case_legacy_d01_schema():
    raw = {
        "id": "cr_py_01",
        "query": "Khóa Python?",
        "intent": "course_rec",
        "competency": "Python",
        "gold_course_codes": ["CRS_LANG_L_PY_01"],
    }
    case = _normalize_case(raw)
    assert case["question"] == "Khóa Python?"
    assert case["expected_courses"] == ["CRS_LANG_L_PY_01"]


def test_route_acceptable_pathfinding():
    allowed = acceptable_routes_for_gold_intent("pathfinding")
    assert "pathfinding" in allowed
    assert route_acceptable("pathfinding", "pathfinding")
    assert route_acceptable("pathfinding", "roadmap_followup")
    assert not route_acceptable("pathfinding", "slot_fill")


def test_route_acceptable_skills_gap():
    allowed = acceptable_routes_for_gold_intent("skills_gap")
    assert "roadmap_followup" in allowed
    assert route_acceptable("skills_gap", "roadmap_followup")
    assert route_acceptable("skills_gap", "competency_slot_fill")
    assert not route_acceptable("skills_gap", "slot_fill")


def test_flatten_known_skills_dedupes():
    skills = _flatten_known_skills(
        {"CT_LANG": ["Python", "SQL"], "CT_TOOL": ["python", "Git"]}
    )
    assert skills == ["Python", "SQL", "Git"]


def test_seed_session_sets_career_and_profile_for_skills_gap():
    state = SessionState(session_id="eval-test")
    chat = MagicMock()
    chat._sessions = MagicMock()
    chat._sessions.get_or_create = AsyncMock(return_value=state)
    chat._sessions.save = AsyncMock()

    case = {
        "id": "sg_mle_01",
        "intent": "skills_gap",
        "question": "Gap?",
        "expected_careers": ["Machine Learning Engineer"],
        "expected_skills": [],
        "expected_courses": [],
        "session_setup": {
            "career": "Machine Learning Engineer",
            "known_by_type": {"CT_LANG": ["Python"]},
        },
    }

    asyncio.run(_seed_session(chat, "eval-test", case))

    assert state.career == "Machine Learning Engineer"
    assert state.profile is not None
    assert state.profile.profile_completed is True
    assert "Python" in state.profile.known_skills
    assert state.phase == "gap_summary"


def test_seed_session_career_from_expected_careers():
    state = SessionState(session_id="eval-pf")
    chat = MagicMock()
    chat._sessions = MagicMock()
    chat._sessions.get_or_create = AsyncMock(return_value=state)
    chat._sessions.save = AsyncMock()

    case = {
        "id": "pf_ds_01",
        "intent": "pathfinding",
        "question": "Lộ trình?",
        "expected_careers": ["Data Scientist"],
        "expected_skills": [],
        "expected_courses": [],
    }

    asyncio.run(_seed_session(chat, "eval-pf", case))
    assert state.career == "Data Scientist"


def test_cohort_for_case_defaults():
    assert _cohort_for_case({"gold_source": "quality_gold_v2.1"}) == "v21_legacy"
    assert _cohort_for_case({"gold_cohort": "v22_new14"}) == "v22_new14"


def test_aggregate_by_cohort():
    cases = [
        {"id": "a", "gold_cohort": "v21_legacy"},
        {"id": "b", "gold_cohort": "v22_new14"},
    ]
    rows = [
        EvalRow("a", "pathfinding", "q", "", JudgeScores(1.0, 1.0, True), {}, run_status=RUN_STATUS_VALID),
        EvalRow("b", "course_rec", "q", "", JudgeScores(0.5, 0.5, True), {}, run_status=RUN_STATUS_ROUTE_MISMATCH),
    ]
    by = aggregate_by_cohort(rows, cases)
    assert by["v21_legacy"]["valid_n"] == 1
    assert by["v22_new14"]["route_mismatch_n"] == 1
