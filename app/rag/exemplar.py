from __future__ import annotations

import logging
from typing import Any

from app.db.engine import database_enabled
from app.db.feedback_repository import FeedbackRepository
from app.rag.embeddings import EmbeddingClient

logger = logging.getLogger(__name__)


class ExemplarRetriever:
    """Retrieve 2–3 approved chat turns similar to current query (embedding cosine)."""

    def __init__(
        self,
        *,
        feedback_repo: FeedbackRepository | None = None,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self._feedback = feedback_repo or FeedbackRepository()
        self._embedder = embedder or EmbeddingClient()
        self._cache: list[dict[str, Any]] | None = None

    async def fetch_examples(self, query: str, *, top_k: int = 2) -> list[str]:
        if not database_enabled() or not self._embedder.available:
            return []
        try:
            rows = await self._feedback.list_approved_messages(limit=200)
        except Exception as exc:
            logger.warning("exemplar list failed: %s", exc)
            return []
        if not rows:
            return []

        texts = [r["content"] for r in rows]
        try:
            q_vec = self._embedder.embed([query])[0]
            doc_vecs = self._embedder.embed(texts)
        except Exception as exc:
            logger.warning("exemplar embed failed: %s", exc)
            return []

        scored: list[tuple[float, str]] = []
        for row, vec in zip(rows, doc_vecs):
            sim = _cosine(q_vec, vec)
            scored.append((sim, row["content"][:600]))
        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored[:top_k] if t.strip()]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
