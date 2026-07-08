"""
Adapter tìm kiếm Qdrant — tương thích query_points (API mới) và search (API cũ).

Tránh rơi vào fallback khi client chỉ hỗ trợ một trong hai API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from qdrant_client.models import Filter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QdrantHit:
    score: float
    payload: dict[str, Any]


def _normalize_hit(raw: Any) -> QdrantHit:
    score = float(getattr(raw, "score", None) or 0.0)
    payload = getattr(raw, "payload", None) or {}
    if not isinstance(payload, dict):
        payload = dict(payload) if payload else {}
    return QdrantHit(score=score, payload=payload)


def _search_query_points(
    client: Any,
    *,
    collection_name: str,
    query_vector: list[float],
    limit: int,
    query_filter: Filter | None,
) -> list[QdrantHit]:
    response = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )
    points = getattr(response, "points", None) or []
    return [_normalize_hit(p) for p in points]


def _search_legacy(
    client: Any,
    *,
    collection_name: str,
    query_vector: list[float],
    limit: int,
    query_filter: Filter | None,
) -> list[QdrantHit]:
    hits = client.search(
        collection_name=collection_name,
        query_vector=query_vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    )
    return [_normalize_hit(h) for h in hits or []]


def search_vectors(
    client: Any,
    *,
    collection_name: str,
    query_vector: list[float],
    limit: int,
    query_filter: Filter | None = None,
) -> list[QdrantHit]:
    """
    Tìm vector trong collection — tự chọn API phù hợp với phiên bản qdrant-client.

    Nếu client có ``query_points`` (≥1.7) thì chỉ dùng API mới; ngược lại dùng ``search``.
    Không fallback giữa hai API khi một API lỗi runtime (để caller xử lý retry/filter).
    """
    if hasattr(client, "query_points"):
        return _search_query_points(
            client,
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter,
        )

    if hasattr(client, "search"):
        return _search_legacy(
            client,
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter,
        )

    raise RuntimeError(
        "Qdrant client has neither query_points nor search — upgrade qdrant-client"
    )
