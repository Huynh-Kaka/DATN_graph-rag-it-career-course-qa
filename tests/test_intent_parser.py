from app.intent.parser import fallback_route, parse_route_json, strip_json_fence


def test_strip_json_fence():
    raw = '```json\n{"domain":"in","intent":"slot_fill"}\n```'
    assert strip_json_fence(raw).startswith('{"domain"')


def test_parse_route_json():
    raw = """
    {
      "domain": "in",
      "intent": "pathfinding",
      "entities": {"career": "Data Analyst", "competency": null},
      "confidence": "high",
      "missing_slots": []
    }
    """
    route = parse_route_json(raw)
    assert route.domain == "in"
    assert route.intent == "pathfinding"
    assert route.entities.career == "Data Analyst"


def test_fallback_route():
    route = fallback_route()
    assert route.intent == "slot_fill"
    assert route.domain == "in"
