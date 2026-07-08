from app.db.profile_snapshot import ProfileSnapshot
from app.graph.models import CompetencyItem, PathfindingResult
from app.graph.skills_gap import apply_skills_gap_to_result, build_gap_skill_names
from app.services.advisory_service import AdvisoryService
from app.services.roadmap_followup import RoadmapFollowupService


def test_merge_gap_labels_excludes_cross_bucket_duplicates():
    pf = PathfindingResult(
        found=True,
        career_name="Backend Dev",
        skills_known=[CompetencyItem(name="Python", kind="ProgrammingLanguage")],
        skills_missing=[CompetencyItem(name="SQL", kind="ProgrammingLanguage")],
    )
    advice = {
        "skills_gap": {
            "missing": ["python", "Docker"],
            "weak": ["SQL", "Python", "Git"],
        }
    }
    known, missing, weak = RoadmapFollowupService._merge_gap_labels(
        pf, advice, ["python"]
    )

    known_keys = {label.lower() for label in known}
    missing_keys = {label.lower() for label in missing}
    weak_keys = {label.lower() for label in weak}

    assert "python" in known_keys
    assert "python" not in missing_keys
    assert "sql" in missing_keys
    assert "docker" in missing_keys
    assert "sql" not in weak_keys
    assert "python" not in weak_keys
    assert "git" in weak_keys


def test_merge_gap_labels_prefix_normalization():
    pf = PathfindingResult(
        found=True,
        career_name="Backend Dev",
        skills_known=[CompetencyItem(name="Platform: Python", kind="ProgrammingLanguage")],
        skills_missing=[
            CompetencyItem(name="python", kind="ProgrammingLanguage"),
            CompetencyItem(name="SQL", kind="ProgrammingLanguage"),
        ],
    )
    known, missing, weak = RoadmapFollowupService._merge_gap_labels(pf, None, [])
    missing_keys = {label.lower() for label in missing}
    assert "python" not in missing_keys
    assert "sql" in missing_keys


def test_build_gap_skill_names_disjoint_and_caps():
    pf = PathfindingResult(
        found=True,
        career_name="Data Analyst",
        competencies=[
            CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY", priority=1),
            CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL", priority=2),
            CompetencyItem(name="Power BI", kind="Tool", code="T_POWERBI", priority=3),
            CompetencyItem(name="Docker", kind="Tool", code="T_DOCKER", priority=4),
        ],
    )
    apply_skills_gap_to_result(pf, ["python", "sql"])
    missing, weak = build_gap_skill_names(pf, max_missing=8, max_weak=3)

    assert "Python" not in missing
    assert "SQL" not in missing
    assert "Power BI" in missing
    assert len(weak) <= 3
    missing_keys = {m.lower() for m in missing}
    for w in weak:
        assert w.lower() not in missing_keys


class _StubGraph:
    def pathfinding(self, career: str, *, known_skills: list[str] | None = None):
        pf = PathfindingResult(
            found=True,
            career_name="Data Analyst",
            competencies=[
                CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY"),
                CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL"),
                CompetencyItem(name="Power BI", kind="Tool", code="T_POWERBI"),
            ],
        )
        apply_skills_gap_to_result(pf, list(known_skills or []))
        return pf

    def close(self) -> None:
        pass


def test_fallback_advice_uses_graph_pathfinding():
    profile = ProfileSnapshot(
        profile_id="p1",
        background="student",
        role="data",
        role_note=None,
        known_skills=["python", "sql"],
        weekly_time=None,
        goals=[],
        initial_question=None,
    )
    svc = AdvisoryService(graph=_StubGraph(), llm=None)
    advice = svc._fallback_advice(profile)

    missing_lower = {s.lower() for s in advice["skills_gap"]["missing"]}
    assert "python" not in missing_lower
    assert "sql" not in missing_lower
    assert "power bi" in missing_lower
    assert advice["skills_gap"]["weak"]
    for w in advice["skills_gap"]["weak"]:
        assert w.lower() not in missing_lower
