from unittest.mock import MagicMock

from app.graph.models import CourseItem
from app.graph.queries.career_multihop import fetch_courses_for_career_skills
from app.services.roadmap_followup import RoadmapFollowupService


def _mock_multihop_rows():
    return [
        {
            "career_name": "Backend Developer",
            "career_code": "BE",
            "competency_name": "Python",
            "competency_code": "L_PY",
            "competency_kind": "ProgrammingLanguage",
            "priority": 1,
            "courses": [
                {
                    "course_name": "Python 101",
                    "course_code": "PY101",
                    "coverage_level": 3,
                },
                {
                    "course_name": "Python Advanced",
                    "course_code": "PY201",
                    "coverage_level": 1,
                },
            ],
        },
        {
            "career_name": "Backend Developer",
            "career_code": "BE",
            "competency_name": "SQL",
            "competency_code": "L_SQL",
            "competency_kind": "ProgrammingLanguage",
            "priority": 2,
            "courses": [
                {
                    "course_name": "SQL Basics",
                    "course_code": "SQL01",
                    "coverage_level": 2,
                }
            ],
        },
    ]


def test_fetch_courses_for_career_skills_single_query():
    session = MagicMock()
    session.run.return_value = _mock_multihop_rows()
    client = MagicMock()
    client.available = True
    client.competency_labels.return_value = ("ProgrammingLanguage",)
    client.session.return_value.__enter__.return_value = session

    result = fetch_courses_for_career_skills(
        client, "Backend Developer", ["Python", "SQL"], max_per_skill=2
    )

    assert result.found is True
    assert len(result.blocks) == 2
    assert result.blocks[0].competency_name == "Python"
    assert result.blocks[0].courses[0].course_name == "Python 101"
    session.run.assert_called_once()
    kwargs = session.run.call_args.kwargs
    assert kwargs["career"] == "Backend Developer"
    assert "python" in kwargs["skill_names_lower"]


def test_fetch_courses_sorted_by_coverage_level():
    session = MagicMock()
    session.run.return_value = _mock_multihop_rows()
    client = MagicMock()
    client.available = True
    client.competency_labels.return_value = ("ProgrammingLanguage",)
    client.session.return_value.__enter__.return_value = session

    result = fetch_courses_for_career_skills(client, "Backend Developer", ["Python"])
    codes = [c.course_code for c in result.blocks[0].courses]
    assert codes[0] == "PY101"


class _MultihopGraph:
    def __init__(self) -> None:
        self.calls = 0

    def courses_for_career_skills(self, career, skill_names, *, max_per_skill=4, **kwargs):
        self.calls += 1
        from app.graph.models import CareerSkillCoursesResult, SkillCoursesBlock

        blocks = [
            SkillCoursesBlock(
                competency_name=skill,
                courses=[CourseItem(course_name=f"Course for {skill}", course_code=f"C_{skill}")],
            )
            for skill in skill_names
        ]
        return CareerSkillCoursesResult(found=True, career_name=career, blocks=blocks)


def test_roadmap_followup_uses_single_multihop_call():
    graph = _MultihopGraph()
    svc = RoadmapFollowupService(graph=graph)
    blocks = svc._fetch_courses_for_skills(
        "Backend Developer",
        ["Python", "SQL", "Docker", "Kubernetes", "Git", "Linux", "Redis"],
    )
    assert graph.calls == 1
    assert len(blocks) == 7
    assert blocks[0]["skill"] == "Python"
    assert blocks[0]["found"] is True


def test_multihop_reduces_neo4j_round_trips():
    """Batch multi-hop = 1 session.run; sequential per-skill = N runs."""
    rows = _mock_multihop_rows()
    session = MagicMock()
    session.run.return_value = rows
    client = MagicMock()
    client.available = True
    client.competency_labels.return_value = ("ProgrammingLanguage",)
    client.session.return_value.__enter__.return_value = session

    fetch_courses_for_career_skills(
        client, "Backend Developer", ["Python", "SQL", "Docker"]
    )
    assert session.run.call_count == 1

    session.run.reset_mock()
    for skill in ["Python", "SQL", "Docker"]:
        fetch_courses_for_career_skills(client, "Backend Developer", [skill])
    assert session.run.call_count == 3
