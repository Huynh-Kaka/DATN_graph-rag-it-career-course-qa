from app.generator.validator import validate_and_strip_hallucinated_citations


def test_strips_unknown_course_citation():
    snap = {"courses": [{"course_code": "PY101"}]}
    text = "Khóa tốt [Course: PY101] và [Course: FAKE99]."
    cleaned, had = validate_and_strip_hallucinated_citations(text, graph_snapshot=snap)
    assert "[Course: PY101]" in cleaned
    assert "FAKE99" not in cleaned
    assert had is True
