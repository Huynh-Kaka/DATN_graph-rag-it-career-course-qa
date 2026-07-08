"""Tests for scripts/eval_retrieval.py helpers (D-02)."""

from scripts.eval_retrieval import (
    _build_metric_rows,
    _has_gold,
    _markdown_table,
    _parse_k_values,
    _relevance_vector,
)


class _Doc:
    def __init__(self, payload: dict):
        self.payload = payload


def test_parse_k_values():
    assert _parse_k_values("5,10") == [5, 10]
    assert _parse_k_values("10,5,5") == [5, 10]


def test_has_gold():
    assert _has_gold({"gold_ids": ["Backend Developer"]}) is True
    assert _has_gold({"gold_ids": [], "gold_competency": "Python"}) is True
    assert _has_gold({"gold_ids": [], "gold_competency": ""}) is False


def test_relevance_vector_pads_short_results():
    row = {
        "gold_field": "career_name",
        "gold_ids": ["Backend Developer"],
    }
    docs = [
        _Doc({"title": "Other", "career_name": "Other"}),
        _Doc({"title": "Backend Developer", "career_name": "Backend Developer"}),
    ]
    rels = _relevance_vector(docs, row, max_k=5)
    assert rels == [0, 1, 0, 0, 0]


def test_build_metric_rows_includes_overall_and_doc_types():
    grouped = {
        "overall": [[1, 0, 0, 0, 0], [0, 1, 0, 0, 0]],
        "career": [[1, 0, 0, 0, 0]],
        "course": [[0, 1, 0, 0, 0]],
    }
    grouped_n_rel = {
        "overall": [2, 1],
        "career": [2],
        "course": [1],
    }
    rows = _build_metric_rows(grouped, grouped_n_rel, [5])
    scopes = {(r.scope, r.doc_type) for r in rows}
    assert ("overall", "all") in scopes
    assert ("by_doc_type", "career") in scopes
    assert ("by_doc_type", "course") in scopes


def test_markdown_table_format():
    from app.eval.retrieval_metrics import RetrievalMetricRow

    rows = [
        RetrievalMetricRow(
            scope="overall",
            doc_type="all",
            k=5,
            n_queries=10,
            recall=0.9,
            precision=0.2,
            mrr=0.75,
            ndcg=0.8,
        )
    ]
    md = _markdown_table(rows)
    assert "| Scope | doc_type | k |" in md
    assert "HitRate@k" in md
    assert "90.00%" in md
    assert "0.7500" in md
