"""
Build index corpus JSONL from Neo4j + domain_aliases (+ optional enriched descriptions).

Chạy: python scripts/build_index_corpus.py --out data/index_corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.graph.neo4j_client import Neo4jClient
from app.rag.corpus_builder import (
    _COMPETENCY_LABELS,
    build_career_index_text,
    build_competency_index_text_with_relations,
    build_course_index_text,
    _load_enriched,
)

_CYPHER_RELATIONS = """
MATCH (src)-[r]->(dst)
WHERE type(r) IN $rel_types
  AND src.item_code IS NOT NULL
  AND dst.item_code IS NOT NULL
RETURN src.item_code AS from_code,
       type(r) AS rel_type,
       dst.item_code AS to_code,
       coalesce(dst.item_name, dst.item_code) AS to_name,
       r.note AS note
"""

_CYPHER_COURSES = """
MATCH (course:Course)
OPTIONAL MATCH (course)-[:PROVIDED_BY]->(org:Organization)
OPTIONAL MATCH (course)-[:AT_LEVEL]->(lvl:Level)
OPTIONAL MATCH (course)-[:HAS_SUBTITLE]->(sub:Subtitle)
OPTIONAL MATCH (course)-[teach]->(comp)
WHERE type(teach) STARTS WITH 'TEACH_'
RETURN DISTINCT
  course.course_code AS course_code,
  coalesce(course.course_name, course.course_code) AS course_name,
  course.description AS description,
  org.org_name AS organization,
  lvl.level_name AS level,
  sub.subtitle_name AS subtitle,
  collect(DISTINCT coalesce(comp.item_name, comp.item_code)) AS competencies
"""

_CYPHER_CAREERS = """
MATCH (c:Career)
OPTIONAL MATCH (c)-[:IN_INDUSTRY]->(i:Industry)
OPTIONAL MATCH (c)-[:IN_TAXONOMY]->(t:Taxonomy)
RETURN c.career_code AS career_code,
       c.career_name AS career_name,
       i.name AS industry,
       t.name AS taxonomy
"""

_CYPHER_COMPETENCIES = """
UNWIND $labels AS lbl
CALL {
  WITH lbl
  MATCH (n)
  WHERE lbl IN labels(n) AND n.item_name IS NOT NULL
  RETURN lbl AS kind, n.item_code AS item_code, n.item_name AS item_name,
         n.description AS description
}
RETURN kind, item_code, item_name, description
"""


def _point_id(doc_type: str, canonical_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_type}:{canonical_id}"))


_EDGE_REL_TYPES = frozenset({"BUILT_ON", "VALIDATES", "REQUIRES"})


def _build_edge_index_text(
    *,
    from_code: str,
    from_name: str,
    rel_type: str,
    to_code: str,
    to_name: str,
) -> str:
    return (
        f"Quan hệ competency: {from_name} ({from_code}) "
        f"{rel_type} {to_name} ({to_code}). "
        f"Để học {from_name} cần {to_name} trước. "
        f"Tiên quyết prerequisite học trước."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "data" / "index_corpus.jsonl",
    )
    parser.add_argument(
        "--skip-coverage-guard",
        action="store_true",
        help="Skip validate_graph_coverage fail-fast (dev only)",
    )
    parser.add_argument("--min-relation-edges", type=int, default=30)
    args = parser.parse_args()

    if not args.skip_coverage_guard:
        from scripts.validate_graph_coverage import check_coverage_threshold

        stats, ok = check_coverage_threshold(
            min_relation_edges=args.min_relation_edges,
            min_coverage=0.0,
            use_neo4j=True,
            warn_only=False,
        )
        print(
            f"Coverage guard: edges={stats['relation_edges']} "
            f"coverage={stats['coverage_ratio']:.1%}"
        )
        if not ok:
            sys.exit(1)

    neo = Neo4jClient()
    if not neo.available:
        print("ERROR: Neo4j unavailable")
        sys.exit(1)

    enriched = _load_enriched()
    chunks: list[dict] = []
    rel_types = [
        "BUILT_ON",
        "VALIDATES",
        "SUPPORTS",
        "REQUIRES",
        "REQUIRES_KNOWLEDGE",
        "PREFERS_LANG",
    ]
    outgoing_by_code: dict[str, list[dict]] = {}

    with neo.session() as session:
        for rel in session.run(_CYPHER_RELATIONS, rel_types=rel_types).data():
            src = str(rel.get("from_code") or "").strip()
            if not src:
                continue
            outgoing_by_code.setdefault(src, []).append(rel)

        for row in session.run(_CYPHER_CAREERS).data():
            name = row.get("career_name")
            if not name:
                continue
            cid = str(row.get("career_code") or name)
            chunks.append(
                {
                    "doc_type": "career",
                    "canonical_id": cid,
                    "title": name,
                    "point_id": _point_id("career", cid),
                    "index_text": build_career_index_text(row, enriched),
                    "payload": {
                        "career_code": row.get("career_code"),
                        "career_name": name,
                    },
                }
            )

        comp_rows = session.run(_CYPHER_COMPETENCIES, labels=_COMPETENCY_LABELS).data()
        for row in comp_rows:
            code = row.get("item_code")
            name = row.get("item_name")
            if not code and not name:
                continue
            cid = str(code or name)
            chunks.append(
                {
                    "doc_type": "competency",
                    "canonical_id": cid,
                    "title": name or cid,
                    "point_id": _point_id("competency", cid),
                    "index_text": build_competency_index_text_with_relations(
                        row,
                        enriched,
                        outgoing=outgoing_by_code.get(cid),
                    ),
                    "payload": {
                        "item_code": code,
                        "item_name": name,
                        "kind": row.get("kind"),
                        "doc_subtype": "anchor",
                    },
                }
            )

        for src_code, edges in outgoing_by_code.items():
            src_name = next(
                (
                    str(r.get("item_name") or r.get("item_code"))
                    for r in comp_rows
                    if str(r.get("item_code") or "") == src_code
                ),
                src_code,
            )
            for edge in edges:
                rel = str(edge.get("rel_type") or "").strip()
                if rel not in _EDGE_REL_TYPES:
                    continue
                to_code = str(edge.get("to_code") or "").strip()
                to_name = str(edge.get("to_name") or to_code).strip()
                if not to_code:
                    continue
                edge_id = f"{src_code}__{rel}__{to_code}"
                chunks.append(
                    {
                        "doc_type": "competency",
                        "canonical_id": edge_id,
                        "title": f"{src_name} {rel} {to_name}",
                        "point_id": _point_id("competency_edge", edge_id),
                        "index_text": _build_edge_index_text(
                            from_code=src_code,
                            from_name=src_name,
                            rel_type=rel,
                            to_code=to_code,
                            to_name=to_name,
                        ),
                        "payload": {
                            "item_code": src_code,
                            "item_name": src_name,
                            "related_code": to_code,
                            "related_name": to_name,
                            "rel_type": rel,
                            "doc_subtype": "edge",
                        },
                    }
                )

        for row in session.run(_CYPHER_COURSES).data():
            code = row.get("course_code")
            if not code:
                continue
            cid = str(code)
            chunks.append(
                {
                    "doc_type": "course",
                    "canonical_id": cid,
                    "title": row.get("course_name") or cid,
                    "point_id": _point_id("course", cid),
                    "index_text": build_course_index_text(row, enriched),
                    "payload": {
                        "course_code": code,
                        "course_name": row.get("course_name"),
                    },
                }
            )

    neo.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for ch in chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

    by_type: dict[str, int] = {}
    for ch in chunks:
        by_type[ch["doc_type"]] = by_type.get(ch["doc_type"], 0) + 1
    print(f"OK: wrote {len(chunks)} chunks to {args.out}")
    print("Counts:", by_type)


if __name__ == "__main__":
    main()
