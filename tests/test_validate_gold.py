from scripts.validate_gold import validate_gold_rows


def test_validate_hint_pathfinding_ok():
    rows = [
        {
            "id": "pf_01",
            "intent": "pathfinding",
            "query": "làm game dev",
            "career": "Game Developer",
            "entity_hint": True,
            "gold_skills": ["Unity", "C#"],
            "gold_source": "derived_from_retrieval_v2",
        }
    ]
    errors, warnings = validate_gold_rows(rows, career_catalog=set())
    assert errors == []


def test_validate_empty_gold_skills_fails():
    rows = [
        {
            "id": "pf_01",
            "intent": "pathfinding",
            "query": "test",
            "career": "Game Developer",
            "entity_hint": True,
            "gold_skills": [],
            "gold_source": "derived_from_retrieval_v2",
        }
    ]
    errors, _ = validate_gold_rows(rows)
    assert any("empty gold_skills" in e for e in errors)


def test_validate_no_hint_requires_expected_career():
    rows = [
        {
            "id": "nh_01",
            "intent": "pathfinding",
            "query": "muốn làm PM",
            "entity_hint": False,
            "gold_skills": ["Roadmapping"],
            "gold_source": "human_verified_from_excel",
        }
    ]
    errors, _ = validate_gold_rows(rows)
    assert any("expected_career" in e for e in errors)


def test_validate_duplicate_id_fails():
    rows = [
        {
            "id": "dup",
            "intent": "pathfinding",
            "query": "a",
            "career": "QA Engineer",
            "gold_skills": ["Selenium"],
            "gold_source": "derived_from_retrieval_v2",
        },
        {
            "id": "dup",
            "intent": "pathfinding",
            "query": "b",
            "career": "QA Engineer",
            "gold_skills": ["Selenium"],
            "gold_source": "derived_from_retrieval_v2",
        },
    ]
    errors, _ = validate_gold_rows(rows)
    assert any("duplicate id" in e for e in errors)
