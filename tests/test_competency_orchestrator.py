from unittest.mock import MagicMock

from app.graph.models import CompetencyItem, PathfindingResult
from app.services.competency_orchestrator import CompetencyTypeOrchestrator
from app.session.store import SessionState


class _StubGraph:
    def pathfinding_by_type(self, career: str, rel_type: str, *, known_skills=None):
        if rel_type == "NEED_LANG":
            return PathfindingResult(
                found=True,
                career_name=career,
                competencies=[
                    CompetencyItem(name="Python", kind="ProgrammingLanguage"),
                    CompetencyItem(name="SQL", kind="ProgrammingLanguage"),
                ],
            )
        return PathfindingResult(found=True, career_name=career, competencies=[])

    def course_recommendation_by_type(self, competency: str, rel_type: str):
        return MagicMock(found=False, courses=[])


def test_orchestrator_skips_empty_types():
    state = SessionState(session_id="o1", career="Data Analyst")
    orch = CompetencyTypeOrchestrator(graph=_StubGraph())
    prompt = orch.start_collection(state)
    assert "Programming language" in prompt or "language" in prompt.lower()
    assert state.current_competency_type == "CT_LANG"


def test_orchestrator_records_skills_and_advances():
    state = SessionState(session_id="o2", career="Data Analyst")
    orch = CompetencyTypeOrchestrator(graph=_StubGraph())
    orch.start_collection(state)
    turn = orch.handle_turn(state, "python, sql")
    assert turn.handled
    assert "Python" in state.known_by_type.get("CT_LANG", [])
    assert state.competency_type_index >= 1


def test_orchestrator_does_not_swallow_free_question():
    """User hỏi tự do giữa luồng → orchestrator trả handled=False để router xử."""
    state = SessionState(session_id="o3", career="Data Analyst")
    orch = CompetencyTypeOrchestrator(graph=_StubGraph())
    orch.start_collection(state)
    before_index = state.competency_type_index
    turn = orch.handle_turn(state, "tôi muốn hỏi kỹ năng mềm của FE là gì?")
    assert not turn.handled
    assert state.competency_type_index == before_index
    assert not state.known_by_type.get("CT_LANG")


def test_orchestrator_exit_command_jumps_to_gap_summary():
    state = SessionState(session_id="o4", career="Data Analyst")
    orch = CompetencyTypeOrchestrator(graph=_StubGraph())
    orch.start_collection(state)
    turn = orch.handle_turn(state, "xem tổng kết")
    assert turn.handled
    assert state.phase == "gap_summary"
    assert turn.structured and turn.structured.get("type") == "competency_gap_summary"


def test_orchestrator_unknown_skill_does_not_advance():
    """Nếu không nhận diện skill → KHÔNG tăng index, gợi ý lại."""
    state = SessionState(session_id="o5", career="Data Analyst")
    orch = CompetencyTypeOrchestrator(graph=_StubGraph())
    orch.start_collection(state)
    before_index = state.competency_type_index
    turn = orch.handle_turn(state, "abc xyz random")
    assert turn.handled
    assert state.competency_type_index == before_index
    assert turn.structured and turn.structured.get("type") == "competency_collection"


def test_orchestrator_returns_structured_card_with_progress():
    state = SessionState(session_id="o6", career="Data Analyst")
    orch = CompetencyTypeOrchestrator(graph=_StubGraph())
    _, card = orch.start_collection_with_card(state)
    assert isinstance(card, dict)
    assert card.get("type") == "competency_collection"
    assert card.get("step") == 1
    assert card.get("total") == 7
    assert isinstance(card.get("suggested_chips"), list)
    assert isinstance(card.get("progress"), list)
    assert len(card["progress"]) == 7
    assert any(a.get("id") == "exit_flow" for a in card.get("actions", []))
