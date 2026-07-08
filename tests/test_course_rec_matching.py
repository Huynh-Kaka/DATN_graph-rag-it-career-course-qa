from app.graph.queries.course_rec import (
    _competency_search_terms,
    _is_spurious_short_match,
)


def test_extract_cbap_from_vietnamese_question():
    terms = _competency_search_terms("khóa học dạy chứng chỉ CBAP")
    assert "CBAP" in terms


def test_cbap_is_not_spurious_match_with_c():
    assert _is_spurious_short_match("CBAP", "C") is True
    assert _is_spurious_short_match("khóa học CBAP", "C") is True


def test_explicit_c_language_is_allowed():
    assert _is_spurious_short_match("học ngôn ngữ C", "C") is False
    assert _is_spurious_short_match("C", "C") is False


def test_sql_not_matched_as_c():
    assert _is_spurious_short_match("SQL", "C") is True
