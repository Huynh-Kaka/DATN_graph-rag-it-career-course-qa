"""B-02 — RETRIEVAL_STRICT fail-fast vs production fallback."""

from unittest.mock import MagicMock, patch

import pytest

import app.rag.retriever as retriever_mod
from app.rag.retriever import RetrieverUnavailableError, VectorRetriever


def _set_strict(monkeypatch, value: bool) -> None:
    """Patch strict flag trên object settings mà retriever thực sự dùng."""
    monkeypatch.setattr(retriever_mod.settings, "retrieval_strict", value)


def _make_retriever(*, qdrant=None, embedder=None) -> VectorRetriever:
    return VectorRetriever(qdrant=qdrant, embedder=embedder)


def test_strict_raises_on_qdrant_client_failure(monkeypatch):
    _set_strict(monkeypatch, True)
    retriever = _make_retriever()

    with patch(
        "app.rag.retriever.create_qdrant_client",
        side_effect=ConnectionError("connection refused"),
    ):
        with pytest.raises(RetrieverUnavailableError, match="Qdrant client unavailable"):
            retriever._vector_search("backend developer roadmap", limit=3, doc_type=None)


def test_non_strict_returns_fallback_on_qdrant_client_failure(monkeypatch):
    _set_strict(monkeypatch, False)
    retriever = _make_retriever()
    retriever.set_bm25_corpus([])

    with patch(
        "app.rag.retriever.create_qdrant_client",
        side_effect=ConnectionError("connection refused"),
    ):
        docs = retriever._vector_search("backend developer roadmap", limit=3, doc_type=None)

    assert len(docs) == 3
    assert all(d.payload.get("source") == "fallback" for d in docs)


def test_strict_raises_on_embedding_unavailable(monkeypatch):
    _set_strict(monkeypatch, True)
    embedder = MagicMock()
    embedder.available = False
    retriever = _make_retriever(qdrant=MagicMock(), embedder=embedder)

    with pytest.raises(RetrieverUnavailableError, match="Embedding client unavailable"):
        retriever._vector_search("python course", limit=3, doc_type=None)


def test_non_strict_returns_fallback_on_embedding_unavailable(monkeypatch):
    _set_strict(monkeypatch, False)
    embedder = MagicMock()
    embedder.available = False
    retriever = _make_retriever(qdrant=MagicMock(), embedder=embedder)

    docs = retriever._vector_search("python course", limit=3, doc_type=None)

    assert len(docs) == 3
    assert all(d.payload.get("source") == "fallback" for d in docs)


def test_strict_raises_on_qdrant_search_error(monkeypatch):
    _set_strict(monkeypatch, True)
    client = MagicMock()
    client.get_collections.side_effect = RuntimeError("qdrant timeout")
    embedder = MagicMock()
    embedder.available = True
    retriever = _make_retriever(qdrant=client, embedder=embedder)

    with pytest.raises(RetrieverUnavailableError, match="Qdrant search failed"):
        retriever._vector_search("data scientist", limit=3, doc_type=None)


def test_non_strict_returns_fallback_on_qdrant_search_error(monkeypatch):
    _set_strict(monkeypatch, False)
    client = MagicMock()
    client.get_collections.side_effect = RuntimeError("qdrant timeout")
    embedder = MagicMock()
    embedder.available = True
    retriever = _make_retriever(qdrant=client, embedder=embedder)

    docs = retriever._vector_search("data scientist", limit=3, doc_type=None)

    assert len(docs) == 3
    assert all(d.payload.get("source") == "fallback" for d in docs)
