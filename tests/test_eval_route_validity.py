"""D-11 — route validity gate excludes bad runs from D-03 aggregates."""

from unittest.mock import AsyncMock, MagicMock

from app.eval.llm_judge import JudgeScores
from scripts.eval_answer_quality import (
    EvalRow,
    RUN_STATUS_INFRA_ERROR,
    RUN_STATUS_ROUTE_MISMATCH,
    RUN_STATUS_VALID,
    _run_case_once,
    aggregate_valid_rows,
    classify_run_status,
    compute_run_status_rates,
    is_infra_error_message,
)


def _row(
    *,
    intent: str = "pathfinding",
    route: str | None = "pathfinding",
    status: str = RUN_STATUS_VALID,
    faith: float = 0.8,
) -> EvalRow:
    return EvalRow(
        case_id="x",
        intent=intent,
        question="q",
        reply_preview="",
        judge=JudgeScores(faith, 0.7, True),
        citations={"n_citations": 0, "n_valid_citations": 0},
        route_intent=route,
        expected_intent=intent,
        run_status=status,
    )


def test_classify_run_status_valid():
    assert classify_run_status(gold_intent="pathfinding", route_intent="pathfinding", error=None) == RUN_STATUS_VALID


def test_classify_run_status_route_mismatch():
    assert (
        classify_run_status(gold_intent="pathfinding", route_intent="slot_fill", error=None)
        == RUN_STATUS_ROUTE_MISMATCH
    )


def test_classify_run_status_infra_error():
    assert classify_run_status(gold_intent="pathfinding", route_intent=None, error="503 high demand") == RUN_STATUS_INFRA_ERROR


def test_classify_run_status_is_error_not_route_mismatch():
    assert (
        classify_run_status(
            gold_intent="pathfinding",
            route_intent="slot_fill",
            is_error=True,
            reply="503 UNAVAILABLE",
        )
        == RUN_STATUS_INFRA_ERROR
    )


def test_classify_run_status_parse_fallback_route_mismatch():
    assert (
        classify_run_status(
            gold_intent="pathfinding",
            expected_intent="pathfinding",
            route_intent="slot_fill",
            parse_fallback=True,
        )
        == RUN_STATUS_ROUTE_MISMATCH
    )


def test_classify_run_status_infra_reply_marker():
    assert (
        classify_run_status(
            gold_intent="pathfinding",
            route_intent="pathfinding",
            reply="Gemini timeout after 30s",
        )
        == RUN_STATUS_INFRA_ERROR
    )


def test_is_infra_error_message():
    assert is_infra_error_message("Gemini 503 UNAVAILABLE: high demand")
    assert not is_infra_error_message("ValueError: bad input")


def test_aggregate_excludes_route_mismatch_and_infra():
    rows = [
        _row(status=RUN_STATUS_VALID, faith=1.0),
        _row(status=RUN_STATUS_ROUTE_MISMATCH, route="slot_fill", faith=0.1),
        _row(status=RUN_STATUS_INFRA_ERROR, route=None, faith=0.0),
    ]
    overall, by_intent = aggregate_valid_rows(rows)
    assert overall.n == 1
    assert overall.means()["faithfulness"] == 1.0
    assert "pathfinding" in by_intent
    assert by_intent["pathfinding"].n == 1


def test_compute_run_status_rates():
    rows = [
        _row(status=RUN_STATUS_VALID),
        _row(status=RUN_STATUS_ROUTE_MISMATCH, route="slot_fill"),
        _row(status=RUN_STATUS_INFRA_ERROR, route=None),
        _row(status=RUN_STATUS_VALID),
    ]
    rates = compute_run_status_rates(rows)
    assert rates["total"] == 4
    assert rates["valid_n"] == 2
    assert rates["route_mismatch_n"] == 1
    assert rates["infra_error_n"] == 1
    assert rates["route_mismatch_rate"] == 0.25


def test_run_case_once_skips_judge_on_is_error():
    import asyncio

    chat = MagicMock()
    chat._sessions = MagicMock()
    chat._sessions.get_or_create = AsyncMock()
    chat._sessions.save = AsyncMock()
    judge = MagicMock()
    judge.score = MagicMock()

    from app.session.store import SessionState

    state = SessionState(session_id="eval-test")
    chat._sessions.get_or_create.return_value = state

    chat.handle_message = AsyncMock(
        return_value={
            "reply": "503 UNAVAILABLE: high demand",
            "route": {"intent": "slot_fill", "parse_fallback": True},
            "is_error": True,
            "graph": None,
        }
    )

    case = {
        "id": "pf_test",
        "question": "lộ trình backend",
        "intent": "pathfinding",
        "expected_intent": "pathfinding",
        "expected_careers": ["Backend Developer"],
        "expected_skills": ["Python"],
        "expected_courses": [],
    }

    row = asyncio.run(_run_case_once(chat, judge, case, delay=0.0))
    assert row.run_status == RUN_STATUS_INFRA_ERROR
    judge.score.assert_not_called()
