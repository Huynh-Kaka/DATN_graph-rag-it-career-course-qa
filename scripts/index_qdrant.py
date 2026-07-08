"""
Index index_corpus.jsonl into Qdrant + persist BM25 sidecar.

Chạy:
  python scripts/build_index_corpus.py
  python scripts/index_qdrant.py

Collection đã có sẵn — chỉ thêm payload index doc_type (không re-embed):
  python scripts/index_qdrant.py --ensure-index-only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from app.core.config import settings
from app.rag.embeddings import EmbeddingClient
from app.rag.qdrant_client import create_qdrant_client

DEFAULT_CORPUS = PROJECT_ROOT / "data" / "index_corpus.jsonl"
BM25_PATH = PROJECT_ROOT / "data" / "bm25_corpus.json"


def ensure_doc_type_payload_index(client: QdrantClient, collection: str) -> None:
    """Payload index bắt buộc để filter doc_type server-side trên Qdrant Cloud."""
    client.create_payload_index(
        collection_name=collection,
        field_name="doc_type",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    print(f"OK: payload index doc_type on {collection!r}")


def _load_corpus(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Index corpus into Qdrant + BM25 sidecar")
    parser.add_argument(
        "--ensure-index-only",
        action="store_true",
        help="Chỉ tạo payload index doc_type trên collection hiện có (không re-embed)",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help=f"Corpus JSONL path (default: {DEFAULT_CORPUS})",
    )
    parser.add_argument(
        "--delete-collection",
        type=str,
        default=None,
        help="Delete named Qdrant collection and exit (no re-index)",
    )
    args = parser.parse_args()

    client = create_qdrant_client(timeout=30.0)
    collection = settings.qdrant_collection

    if args.delete_collection:
        names = {c.name for c in client.get_collections().collections}
        target = args.delete_collection
        if target in names:
            client.delete_collection(collection_name=target)
            print(f"OK: deleted collection {target!r}")
        else:
            print(f"WARN: collection {target!r} not found — nothing to delete")
        return

    if args.ensure_index_only:
        names = {c.name for c in client.get_collections().collections}
        if collection not in names:
            print(f"ERROR: collection {collection!r} not found")
            sys.exit(1)
        ensure_doc_type_payload_index(client, collection)
        return

    corpus_path = args.corpus
    if not corpus_path.is_file():
        print(f"ERROR: missing {corpus_path} — run build_index_corpus.py first")
        sys.exit(1)

    embedder = EmbeddingClient()
    if not embedder.available:
        print("ERROR: configure EMBEDDING_API_KEY / GEMINI_API_KEY")
        sys.exit(1)

    chunks = _load_corpus(corpus_path)
    if not chunks:
        print("WARN: empty corpus")
        sys.exit(0)

    texts = [ch["index_text"] for ch in chunks]
    vectors = embedder.embed(texts)
    dim = len(vectors[0]) if vectors else settings.embedding_dimensions

    names = {c.name for c in client.get_collections().collections}
    if collection in names:
        client.delete_collection(collection_name=collection)
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    ensure_doc_type_payload_index(client, collection)

    points: list[PointStruct] = []
    bm25_rows: list[dict] = []
    for ch, vec in zip(chunks, vectors):
        pid = ch["point_id"]
        payload = {
            "doc_id": pid,
            "chunk_id": pid,
            "doc_type": ch["doc_type"],
            "canonical_id": ch["canonical_id"],
            "title": ch["title"],
            "text": ch["index_text"],
            **(ch.get("payload") or {}),
        }
        points.append(PointStruct(id=pid, vector=vec, payload=payload))
        bm25_rows.append(
            {
                "doc_id": pid,
                "title": ch["title"],
                "payload": payload,
            }
        )

    client.upsert(collection_name=collection, points=points)
    print(f"OK: indexed {len(points)} chunks into {collection} (dim={dim})")
    if corpus_path.resolve() == DEFAULT_CORPUS.resolve():
        BM25_PATH.parent.mkdir(parents=True, exist_ok=True)
        BM25_PATH.write_text(json.dumps(bm25_rows, ensure_ascii=False), encoding="utf-8")
        print(f"BM25 sidecar: {BM25_PATH}")
    else:
        print(f"SKIP BM25 sidecar (non-default corpus {corpus_path.name})")


if __name__ == "__main__":
    main()
