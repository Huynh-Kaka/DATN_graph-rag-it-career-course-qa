"""D-12 graded retrieval metrics vs binary hit-rate."""

import pytest

from app.eval.retrieval_metrics import (
    aggregate_query_metrics,
    average_precision,
    recall_at_k,
    recall_at_k_full,
)


def test_recall_full_differs_from_hit_rate_when_multi_relevant():
    # 2 relevant total, only 1 in top-3
    rels = [1, 0, 0, 0, 0]
    assert recall_at_k(rels, 5) == 1.0
    assert recall_at_k_full(rels, 5, n_relevant_total=2) == pytest.approx(0.5)


def test_average_precision():
    assert average_precision([1, 0, 1, 0]) == pytest.approx((1.0 + 2 / 3) / 2)


def test_aggregate_includes_map_and_recall_full():
    queries = [[1, 0, 0, 0, 0], [0, 1, 0, 0, 0]]
    hit, prec, mrr, ndcg, recall_full, map_score = aggregate_query_metrics(queries, 5)
    assert hit == pytest.approx(1.0)
    assert recall_full == pytest.approx(1.0)
    assert 0.0 < map_score <= 1.0
