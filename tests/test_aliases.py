from app.intent.career_matcher import CareerMatcher
from app.rag.aliases import (
    resolve_alias_any,
    resolve_career_alias,
    resolve_competency_alias,
    resolve_soft_skill_alias,
    resolve_subject_alias,
)
from app.rag.query_expand import expand_query_vi


def test_resolve_career_vi():
    assert resolve_career_alias("lập trình viên backend") == "Backend Developer"
    assert resolve_career_alias("BE") == "Backend Developer"


def test_resolve_competency():
    assert resolve_competency_alias("học python") == "Python"
    assert resolve_competency_alias("py") == "Python"


def test_resolve_soft_skill():
    assert resolve_soft_skill_alias("kỹ năng giao tiếp") == "Communication"
    assert resolve_soft_skill_alias("teamwork tốt") == "Collaboration"


def test_resolve_subject():
    assert resolve_subject_alias("học oop cơ bản") == "Lap trinh huong doi tuong"
    assert resolve_subject_alias("môn cloud computing") == "Dien toan dam may"


def test_resolve_alias_any():
    out = resolve_alias_any("dev backend cần kỹ năng giao tiếp và học OOP")
    assert out["career"] == "Backend Developer"
    assert out["soft_skill"] == "Communication"
    assert out["subject"] == "Lap trinh huong doi tuong"


def test_expand_query_contains_career():
    out = expand_query_vi("dev backend cần học gì")
    assert "Backend Developer" in out


def test_expand_query_contains_soft_skill():
    out = expand_query_vi("mình muốn cải thiện kỹ năng giao tiếp")
    assert "Soft Skill: Communication" in out


def test_expand_query_contains_subject():
    out = expand_query_vi("mình muốn học OOP")
    assert "Subject: Lap trinh huong doi tuong" in out


def test_career_matcher_via_alias():
    careers = ["Backend Developer", "Frontend Developer"]
    m = CareerMatcher(careers)
    assert m.resolve("dev backend") == "Backend Developer"
