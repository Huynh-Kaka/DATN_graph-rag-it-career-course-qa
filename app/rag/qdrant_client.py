"""Qdrant client factory (local hoặc Qdrant Cloud)."""

from __future__ import annotations

from qdrant_client import QdrantClient

from app.core.config import settings


def create_qdrant_client(*, timeout: float = 5.0) -> QdrantClient:
    kwargs: dict = {"url": settings.qdrant_url, "timeout": timeout}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return QdrantClient(**kwargs)


def qdrant_http_headers() -> dict[str, str]:
    if settings.qdrant_api_key:
        return {"api-key": settings.qdrant_api_key}
    return {}
