"""G2 — multi-turn follow-up for competency_relation."""

from __future__ import annotations

from app.intent.models import IntentEntities, IntentRouteResult, RouteOutcome
from app.session.followup import (
    has_explicit_course_rec_pivot,
    infer_competency_relation_followup,
    maybe_adjust_outcome,
)
from app.session.store import SessionState


def test_infer_followup_short_competency_hint():
    state = SessionState(session_id="s1")
    state.last_intent = "competency_relation"
    hint = infer_competency_relation_followup(state, "Thế còn Angular?")
    assert hint is not None


def test_infer_followup_ignored_wrong_last_intent():
    state = SessionState(session_id="s2")
    state.last_intent = "pathfinding"
    assert infer_competency_relation_followup(state, "Thế còn Angular?") is None


def test_infer_followup_ignored_long_unrelated():
    state = SessionState(session_id="s3")
    state.last_intent = "competency_relation"
    long_q = " ".join(["word"] * 30)
    assert infer_competency_relation_followup(state, long_q) is None


def test_explicit_course_rec_pivot():
    assert has_explicit_course_rec_pivot("Oke cho mình khóa Vue")
    assert not has_explicit_course_rec_pivot("Thế còn Vue?")


def test_relation_followup_blocks_course_rec_override():
    state = SessionState(session_id="s4")
    state.last_intent = "competency_relation"
    route = IntentRouteResult(
        domain="in",
        intent="course_rec",
        entities=IntentEntities(competency="Vue"),
        confidence="high",
        missing_slots=[],
    )
    outcome = RouteOutcome(route=route, reply=None, stop=False)
    adjusted = maybe_adjust_outcome(state, "Thế còn Vue?", outcome)
    assert adjusted.route.intent == "competency_relation"


def test_pivot_allows_course_rec():
    state = SessionState(session_id="s5")
    state.last_intent = "competency_relation"
    route = IntentRouteResult(
        domain="in",
        intent="competency_relation",
        entities=IntentEntities(competency="Vue"),
        confidence="high",
        missing_slots=[],
    )
    outcome = RouteOutcome(route=route, reply=None, stop=False)
    assert has_explicit_course_rec_pivot("Oke cho mình khóa Vue")
    # pivot text should not be treated as relation-only follow-up
    assert not infer_competency_relation_followup(state, "Oke cho mình khóa Vue")
