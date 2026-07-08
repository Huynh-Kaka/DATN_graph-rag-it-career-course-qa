from app.rag.aliases import (
    competencies_from_subject,
    load_aliases,
    resolve_all_career_aliases,
    resolve_all_competency_aliases,
    resolve_abbrev_career,
    resolve_alias_all,
)


def test_resolve_all_competency_aliases_multi():
    found = resolve_all_competency_aliases("mình biết python và sql, đang học react")
    assert "Python" in found
    assert "SQL" in found
    assert "React" in found


def test_resolve_all_career_aliases_in_sentence():
    found = resolve_all_career_aliases("so sánh Backend Developer và Data Analyst")
    assert "Backend Developer" in found
    assert "Data Analyst" in found


def test_competencies_from_subject_oop():
    comps = competencies_from_subject("Lap trinh huong doi tuong")
    assert "Python" in comps
    assert "Java" in comps


def test_resolve_alias_all_merges_subject_competencies():
    out = resolve_alias_all("dev backend học OOP và SQL")
    assert "Backend Developer" in out["careers"]
    assert "SQL" in out["competencies"]
    assert any("Python" == c or "Java" == c for c in out["competencies"])


def test_ambiguous_abbrev_pm_default():
    assert resolve_abbrev_career("PM") == "Product Manager"


def test_upgraded_aliases_has_competencies():
    data = load_aliases()
    assert len(data.get("competencies") or {}) >= 100
