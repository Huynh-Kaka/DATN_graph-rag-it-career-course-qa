"""
Batch-enrich short descriptions via Gemini (one-time), save to data/enriched_descriptions.json.

Chạy: python scripts/enrich_descriptions.py --limit 50
Cần: GEMINI_API_KEY, Neo4j
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

from google import genai
from google.genai import types

from app.core.config import settings
from app.graph.neo4j_client import Neo4jClient

_OUT = PROJECT_ROOT / "data" / "enriched_descriptions.json"

_PROMPT = """Viết đúng 2 câu tiếng Việt mô tả ngắn cho mục sau (khóa học/kỹ năng/nghề IT).
CHỈ dùng thông tin trong metadata, KHÔNG bịa tên khóa học hay kỹ năng không có trong metadata.
Metadata:
{meta}
"""


def _gemini_client():
    if not settings.gemini_api_key:
        return None
    return genai.Client(api_key=settings.gemini_api_key)


def _enrich(client, meta: str) -> str:
    model = settings.generator_model or settings.gemini_model
    resp = client.models.generate_content(
        model=model,
        contents=_PROMPT.format(meta=meta),
        config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=200),
    )
    return (resp.text or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="Max items to enrich this run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = _gemini_client()
    if client is None:
        print("ERROR: GEMINI_API_KEY required")
        sys.exit(1)

    existing: dict[str, str] = {}
    if _OUT.is_file():
        existing = json.loads(_OUT.read_text(encoding="utf-8"))

    neo = Neo4jClient()
    if not neo.available:
        print("ERROR: Neo4j unavailable")
        sys.exit(1)

    todo: list[tuple[str, str]] = []
    with neo.session() as session:
        for row in session.run(
            """
            MATCH (c:Course)
            WHERE c.description IS NULL OR size(trim(coalesce(c.description,''))) < 40
            RETURN c.course_code AS code, c.course_name AS name,
                   c.description AS description LIMIT $lim
            """,
            lim=args.limit,
        ).data():
            key = f"course:{row['code']}"
            if key in existing:
                continue
            meta = json.dumps(row, ensure_ascii=False)
            todo.append((key, meta))

    neo.close()

    if not todo:
        print("Nothing to enrich (or all cached).")
        return

    print(f"Enriching {len(todo)} items...")
    for key, meta in todo:
        if args.dry_run:
            print(f"[dry-run] {key}")
            continue
        try:
            text = _enrich(client, meta)
            existing[key] = text
            _safe_print(f"OK {key}: {text[:80]}...")
            time.sleep(0.5)
        except Exception as exc:
            _safe_print(f"FAIL {key}: {exc}")

    if not args.dry_run:
        _OUT.parent.mkdir(parents=True, exist_ok=True)
        _OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {_OUT}")


if __name__ == "__main__":
    main()
