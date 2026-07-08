from unittest.mock import MagicMock

from app.core.config import settings
from app.rag.retriever import (
    RetrievedDoc,
    VectorRetriever,
    _get_bm25_engine,
    _invalidate_bm25_cache,
    _rrf_fuse,
    _tokenize,
)


def test_tokenize_strips_vietnamese_diacritics():
    tokens = _tokenize("Lập trình viên backend")
    # B-03 underthesea: "Lập trình viên" → lap_trinh_vien; regex fallback: lap, trinh, vien
    assert "backend" in tokens
    assert "lap_trinh_vien" in tokens or "lap" in tokens


def test_rrf_fuse_prefers_docs_in_both_lists():
    vec = [
        RetrievedDoc("a", 0.9, {"doc_id": "a"}),
        RetrievedDoc("b", 0.8, {"doc_id": "b"}),
    ]
    bm25 = [
        RetrievedDoc("b", 4.0, {"doc_id": "b"}),
        RetrievedDoc("c", 3.0, {"doc_id": "c"}),
    ]
    fused = _rrf_fuse(vec, bm25, top_k=3, rrf_k=settings.retrieval_rrf_k)
    keys = [d.payload["doc_id"] for d in fused]

    assert keys[0] == "b"
    assert set(keys) == {"b", "a", "c"}


def test_hybrid_rerank_uses_bm25_and_rrf():
    _invalidate_bm25_cache()
    corpus = [
        (
            "d1",
            "Backend Developer",
            {
                "doc_id": "d1",
                "chunk_id": "d1",
                "title": "Backend Developer",
                "text": "Backend Developer Python SQL API",
                "doc_type": "career",
                "career_name": "Backend Developer",
            },
        ),
        (
            "d2",
            "Frontend Developer",
            {
                "doc_id": "d2",
                "chunk_id": "d2",
                "title": "Frontend Developer",
                "text": "Frontend React CSS HTML",
                "doc_type": "career",
                "career_name": "Frontend Developer",
            },
        ),
        (
            "d3",
            "Python course",
            {
                "doc_id": "d3",
                "chunk_id": "d3",
                "title": "Python for AI",
                "text": "Python machine learning tensorflow",
                "doc_type": "course",
            },
        ),
    ]

    retriever = VectorRetriever(qdrant=MagicMock(), embedder=MagicMock())
    retriever.set_bm25_corpus(corpus)

    vector_docs = [
        RetrievedDoc(
            text="Frontend ...",
            score=0.95,
            payload=corpus[1][2],
        )
    ]
    out = retriever._hybrid_rerank(
        "backend developer sql", vector_docs, top_k=2
    )
    titles = [d.payload.get("title") for d in out]
    assert "Backend Developer" in titles


def test_qdrant_doc_type_filter_fallback():
    client = MagicMock()
    err = Exception('Index required but not found for "doc_type"')
    ok_point = MagicMock(
        score=0.9,
        payload={"doc_type": "career", "title": "Backend Developer", "text": "backend"},
    )
    bad_point = MagicMock(
        score=0.8,
        payload={"doc_type": "course", "title": "Python", "text": "python"},
    )
    client.query_points.side_effect = [
        err,
        MagicMock(points=[ok_point, bad_point]),
    ]
    filt = MagicMock()
    hits = VectorRetriever._query_qdrant_points(
        client,
        query_vector=[0.1, 0.2],
        limit=1,
        query_filter=filt,
        doc_type="career",
    )
    assert len(hits) == 1
    assert hits[0].payload["doc_type"] == "career"


def test_bm25_engine_singleton_cache():
    _invalidate_bm25_cache()
    corpus = [("x", "Python", {"text": "python sql"})]
    e1 = _get_bm25_engine(corpus)
    e2 = _get_bm25_engine(corpus)
    assert e1 is e2
