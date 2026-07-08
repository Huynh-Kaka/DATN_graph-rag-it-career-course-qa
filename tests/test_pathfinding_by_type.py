from unittest.mock import MagicMock

from app.graph.models import CompetencyItem
from app.graph.queries.pathfinding import fetch_pathfinding_by_type


def test_fetch_pathfinding_by_type_parses_skills():
    row = {
        "career_name": "Data Analyst",
        "career_code": "DA",
        "industry": "Analytics",
        "skills": [
            {"name": "Python", "kind": "ProgrammingLanguage", "priority": 1},
            {"name": "SQL", "kind": "ProgrammingLanguage", "priority": 2},
        ],
    }
    session = MagicMock()
    session.run.return_value.single.return_value = row
    client = MagicMock()
    client.available = True
    client.session.return_value.__enter__.return_value = session

    result = fetch_pathfinding_by_type(client, "Data Analyst", "NEED_LANG")

    assert result.found is True
    assert result.career_name == "Data Analyst"
    assert len(result.competencies) == 2
    assert result.competencies[0].name == "Python"
    session.run.assert_called_once()
    call_kwargs = session.run.call_args.kwargs or session.run.call_args[1]
    assert call_kwargs["rel_type"] == "NEED_LANG"


def test_fetch_pathfinding_by_type_empty_career():
    client = MagicMock()
    client.available = True
    result = fetch_pathfinding_by_type(client, "", "NEED_LANG")
    assert result.found is False
    assert "career" in (result.error or "").lower()
