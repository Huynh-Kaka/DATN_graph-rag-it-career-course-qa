from app.graph.formatters import (
    format_competency_relation,
    format_course_rec,
    format_pathfinding,
)
from app.graph.models import (
    CompetencyItem,
    CompetencyRelationEdge,
    CompetencyRelationResult,
    CourseItem,
    CourseRecResult,
    PathfindingResult,
)


def test_format_pathfinding_groups_by_kind():
    result = PathfindingResult(
        found=True,
        career_name="Backend Developer",
        competencies=[
            CompetencyItem(name="Python", kind="ProgrammingLanguage", priority=1),
            CompetencyItem(name="Docker", kind="Tool"),
        ],
    )
    text = format_pathfinding(result)
    assert "Backend Developer" in text
    assert "ProgrammingLanguage" in text
    assert "Python" in text


def test_format_course_rec_lists_courses():
    result = CourseRecResult(
        found=True,
        competency_name="Python",
        courses=[
            CourseItem(
                course_name="Python cơ bản",
                organization="Coursera",
                level="Beginner",
                subtitle="Tiếng Việt",
            )
        ],
    )
    text = format_course_rec(result)
    assert "Python cơ bản" in text
    assert "Coursera" in text


def test_format_competency_relation_natural_language():
    result = CompetencyRelationResult(
        found=True,
        anchor_name="Django",
        anchor_code="F_DJANGO",
        coverage="full",
        outgoing=[
            CompetencyRelationEdge(
                rel_type="BUILT_ON",
                from_code="F_DJANGO",
                from_name="Django",
                to_code="L_PY",
                to_name="Python",
                note="Django dùng Python",
            )
        ],
    )
    text = format_competency_relation(result)
    assert "Python" in text
    assert "BUILT_ON" not in text
    assert "L_PY" not in text
    assert "outgoing" not in text.lower()
    assert "được xây dựng trên" in text or "Django dùng Python" in text
