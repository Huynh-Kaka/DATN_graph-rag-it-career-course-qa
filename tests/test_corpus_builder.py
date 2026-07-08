from app.rag.corpus_builder import build_competency_index_text, build_course_index_text


def test_build_course_index_text_with_competencies():
    row = {
        "course_code": "PY101",
        "course_name": "Python Basics",
        "competencies": ["Python", "SQL"],
        "description": "Intro course",
    }
    text = build_course_index_text(row, {})
    assert "Python Basics" in text
    assert "Từ khóa kỹ năng" in text


def test_build_course_index_text_enriches_subject_alias():
    row = {
        "course_code": "SE201",
        "course_name": "OOP Foundations",
        "competencies": ["OOP"],
    }
    text = build_course_index_text(row, {})
    assert "Lap trinh huong doi tuong" in text


def test_build_competency_index_text_enriches_subject_alias():
    row = {
        "item_code": "SUB-OOP",
        "item_name": "OOP",
        "kind": "Knowledge",
    }
    text = build_competency_index_text(row, {})
    assert "Từ khóa học phần" in text
    assert "Lap trinh huong doi tuong" in text
