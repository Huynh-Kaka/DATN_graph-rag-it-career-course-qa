from app.graph.models import CompetencyItem, PathfindingResult
from app.graph.skills_gap import (
    apply_skills_gap_to_result,
    build_gap_skill_names,
    competency_matches_known_code,
    expand_known_skill_codes,
    resolve_known_item_codes,
)


def test_resolve_python_form_code():
    codes = resolve_known_item_codes(
        ["python"],
        competency_catalog=[
            CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY"),
        ],
    )
    assert codes == {"L_PY"}


def test_competency_matches_known_code_exact():
    comp = CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY")
    assert competency_matches_known_code(comp, {"L_PY"})
    assert not competency_matches_known_code(comp, {"L_SQL"})


def test_apply_skills_gap_to_result_splits_by_item_code():
    result = PathfindingResult(
        found=True,
        career_name="Data Analyst",
        competencies=[
            CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY"),
            CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL"),
            CompetencyItem(name="Power BI", kind="Tool", code="T_POWERBI"),
        ],
    )
    apply_skills_gap_to_result(result, ["python"])
    assert [c.code for c in result.skills_known] == ["L_PY"]
    assert {c.code for c in result.skills_missing} == {"L_SQL", "T_POWERBI"}


def test_build_gap_skill_names_from_applied_result():
    result = PathfindingResult(
        found=True,
        career_name="Data Analyst",
        competencies=[
            CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY", priority=1),
            CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL"),
            CompetencyItem(name="Power BI", kind="Tool", code="T_POWERBI"),
        ],
    )
    apply_skills_gap_to_result(result, ["python"])
    missing, weak = build_gap_skill_names(result)
    assert "Python" in weak
    assert "SQL" in missing
    assert "Power BI" in missing


def test_expand_python_alias_legacy_helper():
    tokens = expand_known_skill_codes(["python"])
    assert "python" in tokens
