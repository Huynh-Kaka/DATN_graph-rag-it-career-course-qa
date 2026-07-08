from app.utils.skill_normalize import normalize_skill_label, normalize_skill_set


def test_normalize_strips_prefix():
    assert normalize_skill_label("Platform: Python") == "python"
    assert normalize_skill_label("Tool: Docker") == "docker"
    assert normalize_skill_label("Framework: React") == "react"


def test_normalize_strips_whitespace_and_lower():
    assert normalize_skill_label("  SQL  ") == "sql"
    assert normalize_skill_label("Python") == "python"


def test_normalize_empty():
    assert normalize_skill_label("") == ""
    assert normalize_skill_label("   ") == ""


def test_normalize_set():
    assert normalize_skill_set(["Platform: Python", "SQL", ""]) == {"python", "sql"}
