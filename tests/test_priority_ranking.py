"""C-01: priority_group & coverage_level ranking."""

from unittest.mock import MagicMock

from app.graph.models import CompetencyItem, CourseItem
from app.graph.queries.course_rec import _parse_courses, fetch_course_recommendations
from app.graph.queries.pathfinding import _parse_skills, fetch_pathfinding
from app.response.structured import (
    coverage_badge,
    course_item_to_chip,
    priority_badge,
    structured_from_pathfinding,
)


def test_priority_badge_labels():
    assert priority_badge(1) == "Cốt lõi"
    assert priority_badge(2) == "Nhóm 2"
    assert priority_badge(None) is None


def test_coverage_badge_labels():
    assert coverage_badge(3) == "Bao phủ 3"
    assert coverage_badge(None) is None


def test_parse_skills_sorts_by_priority_asc():
    raw = [
        {"name": "Docker", "kind": "Platform", "priority": 3},
        {"name": "Python", "kind": "ProgrammingLanguage", "priority": 1},
        {"name": "SQL", "kind": "ProgrammingLanguage", "priority": 2},
    ]
    items = _parse_skills(raw)
    assert [c.name for c in items] == ["Python", "SQL", "Docker"]


def test_parse_skills_seed_before_priority():
    raw = [
        {"name": "Docker", "kind": "Platform", "priority": 1, "is_seed": False},
        {"name": "Python", "kind": "ProgrammingLanguage", "priority": 2, "is_seed": True},
    ]
    items = _parse_skills(raw)
    assert items[0].name == "Python"


def test_parse_courses_sorts_by_coverage_desc():
    raw = [
        {"course_name": "Intro", "coverage_level": 1},
        {"course_name": "Deep Dive", "coverage_level": 3},
        {"course_name": "Intermediate", "coverage_level": 2},
    ]
    items = _parse_courses(raw)
    assert [c.course_name for c in items] == ["Deep Dive", "Intermediate", "Intro"]
    assert items[0].coverage_level == 3


def test_parse_courses_seed_before_coverage():
    raw = [
        {"course_name": "High Cov", "coverage_level": 5, "is_seed": False},
        {"course_name": "Seed Low", "coverage_level": 1, "is_seed": True},
    ]
    items = _parse_courses(raw)
    assert items[0].course_name == "Seed Low"


def test_backend_developer_core_skills_first():
    """Kỹ năng nhóm 1 (cốt lõi) xếp trước nhóm 2+ trong pathfinding."""
    row = {
        "career_name": "Backend Developer",
        "career_code": "BE",
        "industry": "Software",
        "skills": [
            {"name": "Kubernetes", "kind": "Platform", "priority": 3},
            {"name": "Python", "kind": "ProgrammingLanguage", "priority": 1},
            {"name": "REST API", "kind": "Knowledge", "priority": 2},
            {"name": "SQL", "kind": "ProgrammingLanguage", "priority": 1},
        ],
    }
    session = MagicMock()
    session.run.return_value.single.return_value = row
    client = MagicMock()
    client.available = True
    client.session.return_value.__enter__.return_value = session

    result = fetch_pathfinding(client, "Backend Developer")

    assert result.found is True
    names = [c.name for c in result.competencies]
    assert names.index("Python") < names.index("REST API")
    assert names.index("SQL") < names.index("Kubernetes")
    assert result.competencies[0].priority == 1


def test_structured_pathfinding_exposes_priority_badges():
    class _Pf:
        career_name = "Backend Developer"
        skills_known = []
        skills_missing = [
            CompetencyItem(name="Python", kind="ProgrammingLanguage", priority=1),
            CompetencyItem(name="Docker", kind="Platform", priority=3),
        ]

    structured = structured_from_pathfinding(_Pf())
    gap = next(s for s in structured.sections if s.type == "skills_gap")
    assert gap.chips_missing == ["Python", "Docker"]
    assert gap.chips_missing_meta[0]["priority_badge"] == "Cốt lõi"
    assert gap.chips_missing_meta[1]["priority_badge"] == "Nhóm 3"


def test_course_item_to_chip_includes_coverage_badge():
    chip = course_item_to_chip({"course_name": "Full Stack", "coverage_level": 4})
    assert chip["coverage_level"] == 4
    assert chip["coverage_badge"] == "Bao phủ 4"


def test_fetch_course_recommendations_preserves_coverage_order():
    row = {
        "competency_name": "Python",
        "competency_kind": "ProgrammingLanguage",
        "courses": [
            {"course_name": "Basics", "coverage_level": 1},
            {"course_name": "Masterclass", "coverage_level": 4},
        ],
    }
    session = MagicMock()
    session.run.return_value.single.return_value = row
    client = MagicMock()
    client.available = True
    client.competency_labels.return_value = ["ProgrammingLanguage"]
    client.session.return_value.__enter__.return_value = session

    result = fetch_course_recommendations(client, "Python")

    assert result.found is True
    assert result.courses[0].course_name == "Masterclass"
    assert result.courses[0].coverage_level == 4
