from app.rag.confidence import compute_confidence


def test_confidence_found_high():
    score = compute_confidence(
        found=True,
        n_competencies=5,
        route_confidence="high",
    )
    assert score >= 0.7


def test_confidence_not_found_low():
    score = compute_confidence(found=False, parse_fallback=True)
    assert score < 0.5
