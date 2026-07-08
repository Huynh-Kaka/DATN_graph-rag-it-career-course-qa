from app.intent.models import IntentEntities, IntentRouteResult, RouteOutcome
from app.session.context import (
    apply_route_to_state,
    build_router_user_message,
    extract_competency_hint,
    infer_followup_intent,
)
from app.session.followup import maybe_adjust_outcome
from app.session.store import SessionState


def test_router_message_includes_career_context():
    state = SessionState(session_id="a", career="Data Analyst", last_intent="pathfinding")
    state.append_message("user", "Làm Data Analyst cần gì?")
    msg = build_router_user_message(state, "khóa SQL nào phù hợp?")
    assert "Data Analyst" in msg
    assert "khóa SQL" in msg


def test_infer_followup_after_pathfinding():
    state = SessionState(session_id="b", career="Data Analyst", last_intent="pathfinding")
    assert infer_followup_intent(state, "vậy khóa SQL nào?") == "course_rec"


def test_infer_followup_after_competency_gap_summary():
    state = SessionState(
        session_id="b2",
        career="Data Analyst",
        last_intent="competency_slot_fill",
        phase="gap_summary",
    )
    assert infer_followup_intent(state, "gợi ý khóa học SQL") == "course_rec"


def test_extract_competency_sql():
    assert extract_competency_hint("khóa SQL nào tốt") == "SQL"


def test_maybe_adjust_outcome_to_course_rec():
    state = SessionState(session_id="c", career="Data Analyst", last_intent="pathfinding")
    outcome = RouteOutcome(
        route=IntentRouteResult(
            domain="in",
            intent="slot_fill",
            entities=IntentEntities(),
            missing_slots=["competency"],
        ),
        stop=True,
    )
    adjusted = maybe_adjust_outcome(state, "khóa SQL nào?", outcome)
    assert adjusted.route.intent == "course_rec"
    assert adjusted.route.entities.competency == "SQL"
    assert adjusted.route.entities.career == "Data Analyst"
    assert adjusted.stop is False


def test_apply_route_updates_last_intent():
    state = SessionState(session_id="d")
    route = IntentRouteResult(
        domain="in",
        intent="pathfinding",
        entities=IntentEntities(career="Backend Developer"),
    )
    apply_route_to_state(state, route)
    assert state.last_intent == "pathfinding"
    assert state.career == "Backend Developer"
