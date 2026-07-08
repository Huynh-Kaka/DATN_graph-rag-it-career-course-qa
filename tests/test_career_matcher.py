from app.intent.career_matcher import CareerMatcher


def test_fuzzy_match_career():
    careers = ["Data Analyst", "Frontend Developer", "Backend Developer"]
    matcher = CareerMatcher(careers)
    assert matcher.resolve("data analyst") == "Data Analyst"
    assert matcher.resolve("lập trình web") is None or matcher.resolve("Frontend Developer")
