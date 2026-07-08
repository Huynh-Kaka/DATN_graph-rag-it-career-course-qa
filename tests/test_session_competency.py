from app.session.competency_types import (
    COMPETENCY_TYPE_ORDER,
    need_rel_for_type,
    teach_rel_for_type,
)
from app.session.store import SessionState


def test_session_competency_defaults():
    state = SessionState(session_id="x")
    assert state.competency_type_index == 0
    assert state.known_by_type == {}
    assert state.phase == "idle"
    assert state.current_competency_type == "CT_LANG"


def test_record_known_and_all_known():
    state = SessionState(session_id="y", career="Backend Developer")
    state.record_known_for_type("CT_LANG", ["Python", "python", "SQL"])
    assert state.known_by_type["CT_LANG"] == ["Python", "SQL"]
    assert set(state.all_known_skills()) == {"Python", "SQL"}


def test_reset_competency_flow():
    state = SessionState(session_id="z", career="Data Analyst")
    state.competency_type_index = 3
    state.known_by_type = {"CT_LANG": ["Python"]}
    state.phase = "gap_summary"
    state.reset_competency_flow()
    assert state.competency_type_index == 0
    assert state.known_by_type == {}
    assert state.phase == "collecting"


def test_ct_rel_maps():
    assert len(COMPETENCY_TYPE_ORDER) == 7
    assert need_rel_for_type("CT_LANG") == "NEED_LANG"
    assert teach_rel_for_type("CT_CERT") == "TEACH_CERT"
