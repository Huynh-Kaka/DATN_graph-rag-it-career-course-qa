"""
IR metrics for retrieval evaluation (D-02).

Pure Python — không phụ thuộc ranx/numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def precision_at_k(relevances: list[int], k: int) -> float:
    """
    Precision@k = |{relevant docs in top-k}| / k.

    Vị trí thiếu (retriever trả ít hơn k) được coi là không liên quan.
    """
    if k <= 0:
        return 0.0
    top = (relevances + [0] * k)[:k]
    hits = sum(1 for rel in top if rel > 0)
    return hits / k


def recall_at_k(relevances: list[int], k: int) -> float:
    """
    Hit Rate@k (query-level, nhị phân): 1 nếu có ít nhất một tài liệu liên quan
    trong top-k, ngược lại 0. Macro-average trên tập query = Hit Rate@k.

    Lưu ý: đây không phải Recall@k chuẩn IR khi có nhiều relevant/doc — dùng
    ``recall_at_k_full`` cho metric graded.
    """
    if k <= 0:
        return 0.0
    top = (relevances + [0] * k)[:k]
    return 1.0 if any(rel > 0 for rel in top) else 0.0


def recall_at_k_full(relevances: list[int], k: int, *, n_relevant_total: int) -> float:
    """
    Recall@k đầy đủ: |relevant ∩ top-k| / |relevant|.

    ``n_relevant_total`` = tổng số tài liệu liên quan cho query (có thể > k).
    """
    if k <= 0 or n_relevant_total <= 0:
        return 0.0
    top = (relevances + [0] * k)[:k]
    hits = sum(1 for rel in top if rel > 0)
    return min(1.0, hits / n_relevant_total)


def average_precision(relevances: list[int]) -> float:
    """Average Precision (AP) cho một query với relevance nhị phân."""
    hits = 0
    sum_prec = 0.0
    for rank, rel in enumerate(relevances, start=1):
        if rel > 0:
            hits += 1
            sum_prec += hits / rank
    if hits == 0:
        return 0.0
    return sum_prec / hits


def reciprocal_rank(relevances: list[int]) -> float:
    """
    RR(q) = 1 / rank_of_first_relevant, hoặc 0 nếu không có tài liệu liên quan.
    """
    for rank, rel in enumerate(relevances, start=1):
        if rel > 0:
            return 1.0 / rank
    return 0.0


def dcg_at_k(relevances: list[int], k: int) -> float:
    """
    DCG@k với độ liên quan nhị phân:

        DCG@k = Σ_{i=1}^{k} rel_i / log₂(i + 1)

    i là thứ hạng (1-indexed); rel_i ∈ {0, 1}.
    """
    if k <= 0:
        return 0.0
    top = (relevances + [0] * k)[:k]
    return sum(rel / math.log2(i + 1) for i, rel in enumerate(top, start=1) if rel > 0)


def idcg_at_k(*, n_relevant: int, k: int) -> float:
    """
    IDCG@k: DCG lý tưởng khi mọi tài liệu liên quan xếp ở đầu.

    Với relevance nhị phân và n tài liệu liên quan:

        IDCG@k = Σ_{i=1}^{min(n, k)} 1 / log₂(i + 1)
    """
    if k <= 0 or n_relevant <= 0:
        return 0.0
    n = min(n_relevant, k)
    return sum(1.0 / math.log2(i + 1) for i in range(1, n + 1))


def ndcg_at_k(
    relevances: list[int],
    k: int,
    *,
    n_relevant: int | None = None,
) -> float:
    """
    nDCG@k = DCG@k / IDCG@k.

    ``n_relevant`` = số tài liệu liên quan trong top-k (dùng làm IDCG).
    Mặc định đếm từ ``relevances`` — đảm bảo 0 ≤ nDCG ≤ 1 kể cả khi
    nhiều doc cùng khớp một gold (ví dụ trùng career trong index).
    """
    top = (relevances + [0] * k)[:k]
    n_rel = n_relevant if n_relevant is not None else sum(1 for rel in top if rel > 0)
    if n_rel <= 0:
        return 0.0
    ideal = idcg_at_k(n_relevant=n_rel, k=k)
    if ideal == 0.0:
        return 0.0
    return dcg_at_k(relevances, k) / ideal


@dataclass
class RetrievalMetricRow:
    scope: str
    doc_type: str
    k: int
    n_queries: int
    recall: float
    precision: float
    mrr: float
    ndcg: float
    hit_rate: float | None = None
    recall_full: float | None = None
    map_score: float | None = None

    def as_csv_dict(self) -> dict[str, str | int | float]:
        out: dict[str, str | int | float] = {
            "scope": self.scope,
            "doc_type": self.doc_type,
            "k": self.k,
            "n_queries": self.n_queries,
            "recall_at_k": round(self.recall, 6),
            "hit_rate_at_k": round(self.hit_rate if self.hit_rate is not None else self.recall, 6),
            "precision_at_k": round(self.precision, 6),
            "mrr": round(self.mrr, 6),
            "ndcg_at_k": round(self.ndcg, 6),
        }
        if self.recall_full is not None:
            out["recall_full_at_k"] = round(self.recall_full, 6)
        if self.map_score is not None:
            out["map"] = round(self.map_score, 6)
        return out


def mean_metric(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def aggregate_query_metrics(
    per_query_relevances: list[list[int]],
    k: int,
    *,
    n_relevant_totals: list[int] | None = None,
) -> tuple[float, float, float, float, float, float]:
    """Macro-average Hit Rate@k, Precision@k, MRR, nDCG@k, full Recall@k, MAP."""
    if not per_query_relevances:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    precisions = [precision_at_k(rel, k) for rel in per_query_relevances]
    hit_rates = [recall_at_k(rel, k) for rel in per_query_relevances]
    if n_relevant_totals and len(n_relevant_totals) == len(per_query_relevances):
        recalls_full = [
            recall_at_k_full(rel, k, n_relevant_total=n_total)
            for rel, n_total in zip(per_query_relevances, n_relevant_totals)
        ]
    else:
        recalls_full = hit_rates
    rrs = [reciprocal_rank(rel) for rel in per_query_relevances]
    ndcgs = [ndcg_at_k(rel, k) for rel in per_query_relevances]
    maps = [average_precision(rel) for rel in per_query_relevances]
    return (
        mean_metric(hit_rates),
        mean_metric(precisions),
        mean_metric(rrs),
        mean_metric(ndcgs),
        mean_metric(recalls_full),
        mean_metric(maps),
    )
