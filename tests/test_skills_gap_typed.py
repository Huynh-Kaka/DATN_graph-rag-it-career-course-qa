from app.graph.models import CompetencyItem, PathfindingResult
from app.graph.skills_gap import apply_skills_gap_typed, merge_typed_gap_results
from app.session.store import SessionState


class _StubGraph:
    def pathfinding_by_type(self, career: str, rel_type: str, *, known_skills=None):
        if rel_type == "NEED_LANG":
            comps = [
                CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY"),
                CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL"),
            ]
        else:
            comps = [CompetencyItem(name="Docker", kind="Tool", code="T_DOCKER")]
        return PathfindingResult(found=True, career_name=career, competencies=comps)


def test_apply_skills_gap_typed_per_block_by_item_code():
    state = SessionState(session_id="g1", career="Backend Developer")
    state.record_known_for_type("CT_LANG", ["Python"])
    by_type = apply_skills_gap_typed(state, _StubGraph())
    assert "CT_LANG" in by_type
    lang_missing = [c.code for c in by_type["CT_LANG"].skills_missing]
    assert "L_SQL" in lang_missing
    assert "L_PY" in [c.code for c in by_type["CT_LANG"].skills_known]


def test_merge_typed_gap_results():
    pf = PathfindingResult(
        found=True,
        skills_known=[CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY")],
        skills_missing=[CompetencyItem(name="SQL", kind="ProgrammingLanguage", code="L_SQL")],
    )
    known, missing = merge_typed_gap_results({"CT_LANG": pf})
    assert [c.code for c in known] == ["L_PY"]
    assert [c.code for c in missing] == ["L_SQL"]
