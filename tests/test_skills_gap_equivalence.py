"""
C-02: đối chiếu luồng skills-gap cũ (string) vs mới (item_code).

Dùng nhiều ngành nghề trong corpus — không chỉ Backend Developer.
"""

from __future__ import annotations

import warnings

import pytest

from app.graph.models import CompetencyItem, PathfindingResult
from app.graph.skills_gap import (
    apply_skills_gap,
    apply_skills_gap_typed,
    apply_skills_gap_to_result,
    gap_item_codes,
    merge_typed_gap_results,
    pathfinding_from_typed_gap,
)
from app.session.competency_types import need_rel_for_type
from app.session.store import SessionState

# Fixtures theo nhiều career trong retrieval_gold (63 vị trí).
_CAREER_LANG_REQUIREMENTS: dict[str, list[CompetencyItem]] = {
    "Data Scientist": [
        CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY", priority=1),
        CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL", priority=1),
        CompetencyItem(name="R", kind="ProgrammingLanguage", code="L_R", priority=2),
    ],
    "Game Developer": [
        CompetencyItem(name="C#", kind="ProgrammingLanguage", code="L_CS", priority=1),
        CompetencyItem(name="C++", kind="ProgrammingLanguage", code="L_CPP", priority=2),
    ],
    "DevOps Engineer": [
        CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY", priority=1),
        CompetencyItem(name="Bash/Shell", kind="ProgrammingLanguage", code="L_BASH", priority=2),
    ],
    "BI Analyst": [
        CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL", priority=1),
        CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY", priority=2),
    ],
    "Machine Learning Engineer": [
        CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY", priority=1),
        CompetencyItem(name="Java", kind="ProgrammingLanguage", code="L_JAVA", priority=2),
    ],
    "Blockchain Developer": [
        CompetencyItem(name="Solidity", kind="ProgrammingLanguage", code="L_SOLIDITY", priority=1),
        CompetencyItem(name="JavaScript", kind="ProgrammingLanguage", code="L_JS", priority=2),
    ],
}


class _TypedGraphStub:
    """Stub pathfinding_by_type — trả competencies có item_code theo career."""

    def __init__(self, career: str) -> None:
        self.career = career
        self.lang_comps = _CAREER_LANG_REQUIREMENTS.get(
            career,
            [
                CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY"),
                CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL"),
            ],
        )

    def pathfinding_by_type(
        self, career: str, rel_type: str, *, known_skills=None
    ) -> PathfindingResult:
        comps: list[CompetencyItem] = []
        if rel_type == need_rel_for_type("CT_LANG"):
            comps = list(self.lang_comps)
        elif rel_type == need_rel_for_type("CT_TOOL"):
            comps = [
                CompetencyItem(name="Git", kind="Tool", code="T_GIT"),
                CompetencyItem(name="Docker", kind="Tool", code="T_DOCKER"),
            ]
        elif rel_type == need_rel_for_type("CT_PLAT"):
            comps = [
                CompetencyItem(name="Linux", kind="Platform", code="P_LINUX"),
            ]
        return PathfindingResult(
            found=bool(comps),
            career_name=career,
            competencies=comps,
        )


def _run_legacy_flat(career: str, known_inputs: list[str]) -> tuple[list[str], list[str]]:
    comps = _TypedGraphStub(career).lang_comps
    pf = PathfindingResult(found=True, career_name=career, competencies=comps)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        apply_skills_gap(pf, known_inputs)
    return gap_item_codes(pf.skills_known), gap_item_codes(pf.skills_missing)


def _run_code_flat(career: str, known_inputs: list[str]) -> tuple[list[str], list[str]]:
    comps = _TypedGraphStub(career).lang_comps
    pf = PathfindingResult(found=True, career_name=career, competencies=comps)
    apply_skills_gap_to_result(pf, known_inputs)
    return gap_item_codes(pf.skills_known), gap_item_codes(pf.skills_missing)


def _run_roadmap_typed(
    career: str, known_inputs: list[str]
) -> tuple[list[str], list[str]]:
    state = SessionState(session_id="eq-roadmap", career=career)
    by_type = apply_skills_gap_typed(
        state, _TypedGraphStub(career), career=career, extra_known=known_inputs
    )
    pf = pathfinding_from_typed_gap(by_type, career_name=career)
    return gap_item_codes(pf.skills_known), gap_item_codes(pf.skills_missing)


def _run_competency_typed(
    career: str, known_by_type: dict[str, list[str]]
) -> tuple[list[str], list[str]]:
    state = SessionState(session_id="eq-orch", career=career)
    state.known_by_type = dict(known_by_type)
    by_type = apply_skills_gap_typed(state, _TypedGraphStub(career), career=career)
    known, missing = merge_typed_gap_results(by_type)
    return gap_item_codes(known), gap_item_codes(missing)


@pytest.mark.parametrize(
    "career,known_inputs,expected_known,expected_missing",
    [
        ("Data Scientist", ["python"], ["L_PY"], ["L_SQL", "L_R"]),
        ("Game Developer", ["c#"], ["L_CS"], ["L_CPP"]),
        ("DevOps Engineer", ["python"], ["L_PY"], ["L_BASH"]),
        ("BI Analyst", ["sql"], ["L_SQL"], ["L_PY"]),
        ("Machine Learning Engineer", ["python"], ["L_PY"], ["L_JAVA"]),
        ("Blockchain Developer", ["javascript"], ["L_JS"], ["L_SOLIDITY"]),
    ],
)
def test_legacy_vs_code_flat_equivalence(
    career: str,
    known_inputs: list[str],
    expected_known: list[str],
    expected_missing: list[str],
):
    legacy_known, legacy_missing = _run_legacy_flat(career, known_inputs)
    code_known, code_missing = _run_code_flat(career, known_inputs)

    assert sorted(legacy_known) == sorted(code_known) == sorted(expected_known)
    assert sorted(legacy_missing) == sorted(code_missing) == sorted(expected_missing)


@pytest.mark.parametrize("career", list(_CAREER_LANG_REQUIREMENTS.keys()))
def test_roadmap_and_competency_typed_missing_codes_match(career: str):
    """Cùng profile → roadmap (extra_known) và orchestrator (typed bucket) khớp mã thiếu."""
    known_inputs = ["python"]
    roadmap_known, roadmap_missing = _run_roadmap_typed(career, known_inputs)

    state_bucket = {"CT_LANG": ["Python"]}
    orch_known, orch_missing = _run_competency_typed(career, state_bucket)

    assert sorted(roadmap_known) == sorted(orch_known)
    assert sorted(roadmap_missing) == sorted(orch_missing)


def test_form_code_resolves_to_item_code():
    pf = PathfindingResult(
        found=True,
        career_name="Data Analyst",
        competencies=[
            CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY"),
            CompetencyItem(name="Excel", kind="Tool", code="T_EXCEL"),
        ],
    )
    apply_skills_gap_to_result(pf, ["python", "excel"])
    assert gap_item_codes(pf.skills_known) == ["L_PY", "T_EXCEL"]
    assert gap_item_codes(pf.skills_missing) == []
