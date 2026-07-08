from unittest.mock import MagicMock

from app.graph.models import CompetencyItem, CourseItem, PathfindingResult, SkillCoursesBlock
from app.intent.models import IntentEntities, IntentRouteResult, RouteOutcome
from app.services.competency_orchestrator import CompetencyTypeOrchestrator
from app.session.context import is_bulk_missing_courses_request
from app.session.followup import maybe_adjust_outcome
from app.session.store import SessionState


class _StubGraph:
    def pathfinding_by_type(self, career: str, rel_type: str, *, known_skills=None):
        return PathfindingResult(
            found=True,
            career_name=career,
            competencies=[
                CompetencyItem(name="Python", kind="ProgrammingLanguage"),
                CompetencyItem(name="Go", kind="ProgrammingLanguage"),
                CompetencyItem(name="Docker", kind="Tool"),
            ],
            skills_known=[],
            skills_missing=[
                CompetencyItem(name="Go", kind="ProgrammingLanguage"),
                CompetencyItem(name="Java", kind="ProgrammingLanguage"),
                CompetencyItem(name="Kubernetes", kind="Tool"),
            ],
        )

    def courses_for_career_skills(self, career, skill_names, **kwargs):
        blocks = []
        for name in skill_names:
            blocks.append(
                SkillCoursesBlock(
                    competency_name=name,
                    priority=1,
                    courses=[
                        CourseItem(
                            course_name=f"Khóa {name} A",
                            organization="Udemy",
                        )
                    ],
                )
            )
        result = MagicMock()
        result.blocks = blocks
        return result


def test_is_bulk_missing_courses_request():
    assert is_bulk_missing_courses_request("gợi ý khóa học")
    assert is_bulk_missing_courses_request("nên học gì")
    assert not is_bulk_missing_courses_request("gợi ý khóa học SQL")
    assert not is_bulk_missing_courses_request("khóa Python nào phù hợp?")


def test_maybe_adjust_bulk_courses_at_gap_summary():
    state = SessionState(
        session_id="bulk1",
        career="Backend Developer",
        phase="gap_summary",
    )
    outcome = RouteOutcome(
        route=IntentRouteResult(
            domain="in",
            intent="course_rec",
            entities=IntentEntities(competency="Collaboration"),
        ),
        stop=True,
    )
    adjusted = maybe_adjust_outcome(state, "gợi ý khóa học", outcome)
    assert adjusted.route.intent == "competency_slot_fill"


def test_orchestrator_gap_summary_returns_all_missing_courses():
    state = SessionState(session_id="bulk2", career="Backend Developer", phase="gap_summary")
    state.known_by_type = {"CT_LANG": ["Python"]}
    orch = CompetencyTypeOrchestrator(graph=_StubGraph())
    turn = orch.handle_turn(state, "gợi ý khóa học")
    assert turn.handled
    assert state.phase == "course"
    courses = (turn.structured or {}).get("courses_by_skill") or []
    assert len(courses) >= 2
    skills = {b["skill"] for b in courses}
    assert "Go" in skills or "Java" in skills or "Kubernetes" in skills
