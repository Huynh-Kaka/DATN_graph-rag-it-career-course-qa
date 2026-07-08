from unittest.mock import MagicMock

import pytest

from app.rag.qdrant_search import QdrantHit, search_vectors


class _Point:
    def __init__(self, score: float, payload: dict) -> None:
        self.score = score
        self.payload = payload


class _QueryResponse:
    def __init__(self, points: list) -> None:
        self.points = points


def test_search_vectors_uses_query_points_when_available():
    client = MagicMock()
    client.query_points.return_value = _QueryResponse(
        [_Point(0.9, {"text": "hello", "doc_type": "career"})]
    )
    del client.search

    hits = search_vectors(
        client,
        collection_name="career_roadmap",
        query_vector=[0.1, 0.2],
        limit=3,
    )
    assert len(hits) == 1
    assert isinstance(hits[0], QdrantHit)
    assert hits[0].score == 0.9
    assert hits[0].payload["text"] == "hello"
    client.query_points.assert_called_once()


def test_search_vectors_falls_back_to_legacy_search():
    client = MagicMock(spec=[])
    client.search = MagicMock(
        return_value=[_Point(0.7, {"text": "legacy", "title": "T"})]
    )

    hits = search_vectors(
        client,
        collection_name="career_roadmap",
        query_vector=[0.3],
        limit=2,
    )
    assert len(hits) == 1
    assert hits[0].payload["text"] == "legacy"
    client.search.assert_called_once()


def test_search_vectors_propagates_query_points_error_without_search_fallback():
    client = MagicMock()
    client.query_points.side_effect = RuntimeError("new api down")
    client.search = MagicMock(side_effect=RuntimeError("old api down"))

    with pytest.raises(RuntimeError, match="new api down"):
        search_vectors(
            client,
            collection_name="x",
            query_vector=[1.0],
            limit=1,
        )
    client.search.assert_not_called()
