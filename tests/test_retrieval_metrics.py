"""Unit tests for D-02 retrieval IR metrics."""

import math

import pytest

from app.eval.retrieval_metrics import (
    aggregate_query_metrics,
    dcg_at_k,
    idcg_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_precision_at_k():
    assert precision_at_k([1, 0, 0, 0, 0], 5) == pytest.approx(0.2)
    assert precision_at_k([1, 1, 0, 0, 0], 5) == pytest.approx(0.4)
    assert precision_at_k([1], 5) == pytest.approx(0.2)
    assert precision_at_k([], 5) == pytest.approx(0.0)


def test_recall_at_k():
    assert recall_at_k([1, 0, 0], 5) == 1.0
    assert recall_at_k([0, 0, 1], 2) == 0.0
    assert recall_at_k([0, 0, 1], 3) == 1.0


def test_reciprocal_rank():
    assert reciprocal_rank([1, 0, 0]) == pytest.approx(1.0)
    assert reciprocal_rank([0, 0, 1, 0]) == pytest.approx(1 / 3)
    assert reciprocal_rank([0, 0, 0]) == 0.0


def test_dcg_and_idcg_binary():
    assert dcg_at_k([1, 0, 0], 3) == pytest.approx(1 / math.log2(2))
    assert idcg_at_k(n_relevant=1, k=3) == pytest.approx(1 / math.log2(2))


def test_ndcg_at_k_perfect_and_delayed():
    assert ndcg_at_k([1, 0, 0], 3) == pytest.approx(1.0)
    expected = (1 / math.log2(3)) / (1 / math.log2(2))
    assert ndcg_at_k([0, 1, 0], 3) == pytest.approx(expected)
    assert ndcg_at_k([0, 0, 0], 3) == pytest.approx(0.0)


def test_ndcg_empty_ideal():
    assert ndcg_at_k([0, 0], 2) == 0.0


def test_ndcg_never_exceeds_one_with_multiple_hits():
    # Hai doc cùng khớp gold ở hạng 1 và 2 → nDCG = 1.
    assert ndcg_at_k([1, 1, 0, 0, 0], 5) == pytest.approx(1.0)
    # Hai hit nhưng một ở hạng 4 → nDCG < 1.
    assert ndcg_at_k([1, 0, 0, 1, 0], 5) < 1.0


def test_aggregate_query_metrics():
    queries = [
        [1, 0, 0, 0, 0],
        [0, 1, 0, 0, 0],
    ]
    hit_rate, precision, mrr, ndcg, recall_full, map_score = aggregate_query_metrics(queries, 5)
    assert hit_rate == pytest.approx(1.0)
    assert precision == pytest.approx(0.2)
    assert mrr == pytest.approx((1.0 + 0.5) / 2)
    assert 0.0 < ndcg < 1.0
