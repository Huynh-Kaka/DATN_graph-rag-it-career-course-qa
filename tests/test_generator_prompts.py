from app.generator.prompts import build_pathfinding_user_prompt, build_slot_fill_user_prompt
from app.intent.models import IntentEntities, IntentRouteResult
from app.db.profile_snapshot import ProfileSnapshot
from app.session.store import SessionState


def _sample_profile() -> ProfileSnapshot:
    return ProfileSnapshot(
        profile_id="p1",
        background="student",
        role="backend",
        role_note=None,
        known_skills=["python"],
        weekly_time="5to10",
        goals=["roadmap"],
        initial_question=None,
    )


def test_pathfinding_prompt_contains_graph_json():
    state = SessionState(session_id="x", profile=_sample_profile(), career="Backend Developer")
    text = build_pathfinding_user_prompt(
        user_message="Cần học gì?",
        graph_data={"career_name": "Backend Developer", "competencies": []},
        state=state,
    )
    assert "Backend Developer" in text
    assert "Dữ liệu Neo4j" in text
    assert "known_skills" in text


def test_slot_fill_prompt_lists_missing_slots():
    route = IntentRouteResult(
        domain="in",
        intent="slot_fill",
        entities=IntentEntities(),
        missing_slots=["career"],
    )
    state = SessionState(session_id="y")
    text = build_slot_fill_user_prompt(
        user_message="Em muốn làm IT",
        route=route,
        state=state,
    )
    assert "career" in text
    assert "missing_slots" in text
