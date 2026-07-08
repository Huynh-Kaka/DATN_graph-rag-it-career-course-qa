from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.rag.embeddings import EmbeddingClient
from app.rag.qdrant_client import create_qdrant_client
from app.rag.qdrant_search import search_vectors
from app.rag.query_expand import expand_query_vi

logger = logging.getLogger(__name__)


class RetrieverUnavailableError(Exception):
    """Raised when Qdrant/embedding is unavailable and RETRIEVAL_STRICT=1."""


_BM25_PATH = Path(__file__).resolve().parents[2] / "data" / "bm25_corpus.json"

_bm25_engine: BM25Okapi | None = None
_bm25_corpus_key: tuple[str, ...] | None = None


@dataclass
class RetrievedDoc:
    text: str
    score: float
    payload: dict


def _load_bm25_corpus() -> list[tuple[str, str, dict]]:
    if not _BM25_PATH.is_file():
        return []
    try:
        raw = json.loads(_BM25_PATH.read_text(encoding="utf-8"))
        return [(r["doc_id"], r["title"], r["payload"]) for r in raw]
    except Exception as exc:
        logger.warning("Failed to load BM25 corpus: %s", exc)
        return []


def _bm25_cache_key(corpus: list[tuple[str, str, dict]]) -> tuple[str, ...]:
    if not corpus:
        return ()
    return (str(len(corpus)), str(corpus[0][0]), str(corpus[-1][0]))


def _invalidate_bm25_cache() -> None:
    global _bm25_engine, _bm25_corpus_key
    _bm25_engine = None
    _bm25_corpus_key = None


def _get_bm25_engine(corpus: list[tuple[str, str, dict]]) -> BM25Okapi | None:
    """Singleton BM25Okapi — khởi tạo một lần cho mỗi corpus snapshot."""
    global _bm25_engine, _bm25_corpus_key
    if not corpus:
        _invalidate_bm25_cache()
        return None

    key = _bm25_cache_key(corpus)
    if _bm25_engine is not None and _bm25_corpus_key == key:
        return _bm25_engine

    tokenized = [
        _tokenize(f"{title} {payload.get('text', '')}")
        for _, title, payload in corpus
    ]
    if not any(tokenized):
        _invalidate_bm25_cache()
        return None

    _bm25_engine = BM25Okapi(tokenized)
    _bm25_corpus_key = key
    return _bm25_engine


def _unidecode_text(raw: str) -> str:
    try:
        from unidecode import unidecode

        return unidecode(raw)
    except ImportError:
        return raw


def _unidecode_tokens(tokens: list[str]) -> list[str]:
    try:
        from unidecode import unidecode

        return [unidecode(t) for t in tokens]
    except ImportError:
        return tokens


_underthesea_available: bool | None = None
_underthesea_warned = False


def _check_underthesea() -> bool:
    """Lazy-check underthesea; log warning once if missing (B-03 graceful fallback)."""
    global _underthesea_available, _underthesea_warned
    if _underthesea_available is not None:
        return _underthesea_available
    try:
        from underthesea import word_tokenize  # noqa: F401

        _underthesea_available = True
    except ImportError:
        _underthesea_available = False
        if not _underthesea_warned:
            logger.warning(
                "underthesea chưa cài — dùng regex tokenizer cho BM25. "
                "Cài: pip install underthesea (B-03)."
            )
            _underthesea_warned = True
    return _underthesea_available


def _tokenize_regex(text: str) -> list[str]:
    """Fallback: tách từ bằng regex trên chuỗi đã lowercase."""
    normalized = (text or "").lower()
    tokens = [t for t in re.split(r"\W+", normalized) if len(t) > 1]
    if tokens:
        return tokens
    return [t for t in re.findall(r"[a-z0-9+#.]+", normalized) if len(t) > 1]


def _clean_segment_tokens(parts: list[str]) -> list[str]:
    """Giữ chữ, số, underscore (từ ghép underthesea); bỏ token quá ngắn."""
    out: list[str] = []
    for part in parts:
        cleaned = re.sub(r"[^\w+#.]", "", part, flags=re.UNICODE)
        if len(cleaned) > 1:
            out.append(cleaned)
    return out


def _tokenize_with_underthesea(text: str) -> list[str] | None:
    """B-03: word_tokenize(format='text') → từ ghép nối bằng underscore."""
    try:
        from underthesea import word_tokenize

        segmented = word_tokenize(text or "", format="text").lower()
        tokens = _clean_segment_tokens(segmented.split())
        return tokens if tokens else None
    except Exception as exc:
        logger.warning("underthesea tokenize failed: %s", exc)
        return None


def _tokenize(text: str) -> list[str]:
    """B-03: underthesea word segmentation + unidecode; fallback regex nếu thiếu thư viện."""
    raw = text or ""
    if _check_underthesea():
        tokens = _tokenize_with_underthesea(raw)
        if tokens:
            return _unidecode_tokens(tokens)

    normalized = _unidecode_text(raw)
    return _unidecode_tokens(_tokenize_regex(normalized))


def _doc_entity_ids(doc: RetrievedDoc) -> set[str]:
    """Các định danh graph có thể khớp với ``relevant_ids`` (A-03)."""
    payload = doc.payload or {}
    ids: set[str] = set()
    for key in ("canonical_id", "course_code", "item_code", "career_code"):
        val = payload.get(key)
        if val is not None and str(val).strip():
            ids.add(str(val).strip())
    return ids


def _apply_graph_boost(
    docs: List[RetrievedDoc],
    relevant_ids: Optional[set[str]],
    *,
    top_k: int | None = None,
) -> List[RetrievedDoc]:
    """Cộng ``settings.retrieval_graph_boost`` cho doc thuộc subgraph liên quan."""
    if not relevant_ids:
        return docs[:top_k] if top_k is not None else docs

    boost = settings.retrieval_graph_boost
    boosted: list[RetrievedDoc] = []
    for doc in docs:
        score = doc.score
        if _doc_entity_ids(doc) & relevant_ids:
            score += boost
        boosted.append(
            RetrievedDoc(text=doc.text, score=score, payload=doc.payload)
        )
    boosted.sort(key=lambda d: -d.score)
    if top_k is not None:
        return boosted[:top_k]
    return boosted


def _doc_key(doc: RetrievedDoc) -> str:
    payload = doc.payload or {}
    return str(
        payload.get("chunk_id")
        or payload.get("doc_id")
        or payload.get("canonical_id")
        or doc.text[:120]
    )


def _rrf_fuse(
    vector_ranked: list[RetrievedDoc],
    bm25_ranked: list[RetrievedDoc],
    *,
    top_k: int,
    rrf_k: int | None = None,
) -> list[RetrievedDoc]:
    if rrf_k is None:
        rrf_k = settings.retrieval_rrf_k
    """
    Reciprocal Rank Fusion:
    RRF(d) = sum_m 1 / (k + rank_m(d))
    """
    scores: dict[str, float] = {}
    doc_by_key: dict[str, RetrievedDoc] = {}

    for rank, doc in enumerate(vector_ranked, start=1):
        key = _doc_key(doc)
        scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
        doc_by_key.setdefault(key, doc)

    for rank, doc in enumerate(bm25_ranked, start=1):
        key = _doc_key(doc)
        scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
        doc_by_key.setdefault(key, doc)

    fused: list[RetrievedDoc] = []
    for key in sorted(scores.keys(), key=lambda k: -scores[k]):
        base = doc_by_key[key]
        fused.append(
            RetrievedDoc(text=base.text, score=scores[key], payload=base.payload)
        )
        if len(fused) >= top_k:
            break
    return fused


def _is_edge_doc(doc: RetrievedDoc) -> bool:
    payload = doc.payload or {}
    return str(payload.get("doc_subtype") or "").lower() == "edge"


def _cap_edge_docs(
    docs: list[RetrievedDoc],
    *,
    top_k: int,
    max_edge: int | None = None,
) -> list[RetrievedDoc]:
    """G3: limit edge subtype docs in top-k to avoid anchor crowding."""
    cap = max_edge if max_edge is not None else settings.retrieval_max_edge_in_top_k
    if cap < 0 or not docs:
        return docs[:top_k]
    out: list[RetrievedDoc] = []
    edge_count = 0
    for doc in docs:
        if _is_edge_doc(doc):
            if edge_count >= cap:
                continue
            edge_count += 1
        out.append(doc)
        if len(out) >= top_k:
            break
    return out


class VectorRetriever:
    """Qdrant similarity search + BM25Okapi + RRF hybrid rerank."""

    def __init__(
        self,
        *,
        qdrant: QdrantClient | None = None,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self._qdrant = qdrant
        self._embedder = embedder or EmbeddingClient()
        self._bm25_index: list[tuple[str, str, dict]] = _load_bm25_corpus()

    def set_bm25_corpus(self, items: list[tuple[str, str, dict]]) -> None:
        self._bm25_index = items
        _invalidate_bm25_cache()

    def reload_bm25_corpus(self) -> None:
        self._bm25_index = _load_bm25_corpus()
        _invalidate_bm25_cache()

    def _client(self) -> QdrantClient | None:
        if self._qdrant is not None:
            return self._qdrant
        try:
            return create_qdrant_client(timeout=5.0)
        except Exception as exc:
            if settings.retrieval_strict:
                raise RetrieverUnavailableError(
                    f"Qdrant client unavailable: {exc}"
                ) from exc
            logger.warning("Qdrant client unavailable: %s", exc)
            return None

    def _fallback_or_raise(self, message: str, limit: int) -> List[RetrievedDoc]:
        if settings.retrieval_strict:
            raise RetrieverUnavailableError(message)
        logger.warning("%s — returning fallback samples", message)
        return self._fallback_samples(limit)

    def retrieve(self, query: str, top_k: int = 3, *, doc_type: str | None = None) -> List[str]:
        docs = self.retrieve_docs(query, top_k=top_k, doc_type=doc_type)
        return [d.text for d in docs]

    def retrieve_docs(
        self,
        query: str,
        top_k: int = 3,
        *,
        doc_type: str | None = None,
        relevant_ids: Optional[set[str]] = None,
        use_query_expand: bool = True,
        use_bm25: bool = True,
        use_graph_boost: bool = True,
    ) -> List[RetrievedDoc]:
        q = (query or "").strip()
        if not q:
            return []

        expand_relations = bool(
            doc_type == "competency"
            or (
                use_query_expand
                and self._should_expand_relations(q)
            )
        )
        search_q = (
            expand_query_vi(q, expand_relations=expand_relations)
            if use_query_expand
            else q
        )
        pool_limit = (
            settings.retrieval_rrf_pool_size
            if self._bm25_index and use_bm25
            else max(top_k * 4, 12)
        )
        vector_docs = self._vector_search(
            search_q, limit=pool_limit, doc_type=doc_type
        )
        if self._bm25_index and use_bm25:
            vector_docs = self._hybrid_rerank(
                search_q,
                vector_docs,
                top_k=top_k,
                relevant_ids=relevant_ids if use_graph_boost else None,
            )
        else:
            if use_graph_boost:
                vector_docs = _apply_graph_boost(
                    vector_docs, relevant_ids, top_k=top_k
                )
            else:
                vector_docs = vector_docs[:top_k]
        return _cap_edge_docs(vector_docs, top_k=top_k)

    @staticmethod
    def _should_expand_relations(query: str) -> bool:
        try:
            from app.intent.competency_relation_detect import should_route_competency_relation

            return should_route_competency_relation(query)
        except Exception:
            return False

    def _vector_search(
        self, query: str, *, limit: int, doc_type: str | None
    ) -> List[RetrievedDoc]:
        client = self._client()
        if client is None:
            return self._fallback_samples(limit)
        if not self._embedder.available:
            return self._fallback_or_raise("Embedding client unavailable", limit)

        try:
            collections = {c.name for c in client.get_collections().collections}
            if settings.qdrant_collection not in collections:
                msg = f"Qdrant collection {settings.qdrant_collection} missing"
                if settings.retrieval_strict:
                    raise RetrieverUnavailableError(msg)
                logger.info(msg)
                return self._fallback_samples(limit)

            vec = self._embedder.embed([query])[0]
            query_filter = None
            if doc_type:
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="doc_type",
                            match=MatchValue(value=doc_type),
                        )
                    ]
                )

            hits = self._query_qdrant_points(
                client,
                query_vector=vec,
                limit=limit,
                query_filter=query_filter,
                doc_type=doc_type,
            )
            out: List[RetrievedDoc] = []
            for hit in hits:
                payload = hit.payload
                text = str(payload.get("text") or payload.get("title") or "").strip()
                if not text:
                    continue
                out.append(
                    RetrievedDoc(
                        text=text,
                        score=float(hit.score),
                        payload=dict(payload),
                    )
                )
            return out or self._fallback_samples(limit)
        except RetrieverUnavailableError:
            raise
        except Exception as exc:
            return self._fallback_or_raise(f"Qdrant search failed: {exc}", limit)

    @staticmethod
    def _query_qdrant_points(
        client: QdrantClient,
        *,
        query_vector: list[float],
        limit: int,
        query_filter: Filter | None,
        doc_type: str | None,
    ) -> list:
        """Adapter query_points/search; fallback bỏ filter khi Qdrant chưa index doc_type."""
        try:
            return search_vectors(
                client,
                collection_name=settings.qdrant_collection,
                query_vector=query_vector,
                limit=limit,
                query_filter=query_filter,
            )
        except Exception as exc:
            msg = str(exc)
            if not query_filter or "Index required" not in msg:
                raise
            logger.info("Qdrant doc_type index missing — retry without server-side filter")
            hits = search_vectors(
                client,
                collection_name=settings.qdrant_collection,
                query_vector=query_vector,
                limit=max(limit * 3, limit),
                query_filter=None,
            )
            if doc_type:
                hits = [h for h in hits if h.payload.get("doc_type") == doc_type]
            return hits[:limit]

    def _hybrid_rerank(
        self,
        query: str,
        docs: List[RetrievedDoc],
        *,
        top_k: int,
        relevant_ids: Optional[set[str]] = None,
    ) -> List[RetrievedDoc]:
        """B-01: BM25Okapi top-60 + vector top-60 → RRF; A-03: graph-aware boost."""
        bm25 = _get_bm25_engine(self._bm25_index)
        if bm25 is None:
            return _apply_graph_boost(docs, relevant_ids, top_k=top_k)

        query_tokens = _tokenize(query)
        if not query_tokens:
            return _apply_graph_boost(docs, relevant_ids, top_k=top_k)

        bm25_scores = bm25.get_scores(query_tokens)
        bm25_ranked: list[RetrievedDoc] = []
        for idx in sorted(range(len(bm25_scores)), key=lambda i: -bm25_scores[i]):
            score = float(bm25_scores[idx])
            if score <= 0:
                continue
            _, title, payload = self._bm25_index[idx]
            text = str(payload.get("text") or title)
            bm25_ranked.append(
                RetrievedDoc(text=text, score=score, payload=dict(payload))
            )
            pool = settings.retrieval_rrf_pool_size
            if len(bm25_ranked) >= pool:
                break

        pool = settings.retrieval_rrf_pool_size
        vector_ranked = docs[:pool]
        if not bm25_ranked and not vector_ranked:
            return []

        fused = _rrf_fuse(
            vector_ranked,
            bm25_ranked,
            top_k=pool,
            rrf_k=settings.retrieval_rrf_k,
        )
        boosted = _apply_graph_boost(fused, relevant_ids, top_k=top_k)
        return _cap_edge_docs(boosted, top_k=top_k)

    @staticmethod
    def _fallback_samples(limit: int) -> List[RetrievedDoc]:
        samples = [
            RetrievedDoc(
                text="Roadmap: Build 2 backend projects with auth, caching, and deployment.",
                score=0.1,
                payload={"source": "fallback", "doc_type": "course"},
            ),
            RetrievedDoc(
                text="Roadmap: Practice DSA 30 mins/day and contribute to open-source.",
                score=0.1,
                payload={"source": "fallback", "doc_type": "career"},
            ),
            RetrievedDoc(
                text="Khóa học Python cho người mới: fundamentals và project thực hành.",
                score=0.1,
                payload={"source": "fallback", "doc_type": "course"},
            ),
        ]
        return samples[:limit]
