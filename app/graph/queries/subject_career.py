"""
C-03 — Multi-hop học thuật: Subject → Course → Competency → Career.

Schema thực tế (ingest.py): (Course)-[:IN_SUBJECT]->(Subject), không phải HAS_SUBTITLE.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.graph.neo4j_client import Neo4jClient

_CYPHER_SUBJECT_TO_CAREERS = """
MATCH (s:Subject)<-[:IN_SUBJECT]-(c:Course)
MATCH (c)-[r1]->(comp)
WHERE type(r1) STARTS WITH 'TEACH_'
  AND comp.item_name IS NOT NULL
MATCH (career:Career)-[r2]->(comp)
WHERE type(r2) STARTS WITH 'NEED_'
  AND (
    ANY(term IN $search_terms WHERE
      toLower(coalesce(s.subject_name, '')) CONTAINS toLower(term)
      OR toLower(term) CONTAINS toLower(coalesce(s.subject_name, ''))
    )
    OR s.subject_code IN $subject_codes
  )
RETURN DISTINCT
  s.subject_name AS subject,
  s.subject_code AS subject_code,
  c.course_name AS course,
  c.course_code AS course_code,
  coalesce(comp.item_name, comp.item_code) AS competency,
  comp.item_code AS competency_code,
  career.career_name AS career,
  career.career_code AS career_code
ORDER BY career, competency, course
LIMIT $limit
"""


def fetch_subject_to_careers(
    client: Neo4jClient,
    *,
    search_terms: Sequence[str],
    subject_codes: Sequence[str] | None = None,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Truy vấn đa bước Subject → Course → Competency → Career."""
    terms = [str(t).strip() for t in search_terms if str(t).strip()]
    codes = [str(c).strip() for c in (subject_codes or []) if str(c).strip()]
    if not terms and not codes:
        return []
    if not client.available:
        return []

    params = {
        "search_terms": terms,
        "subject_codes": codes,
        "limit": max(1, min(int(limit), 50)),
    }
    try:
        with client.session() as session:
            rows = session.run(_CYPHER_SUBJECT_TO_CAREERS, params).data()
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        item = {
            "subject": str(row.get("subject") or "").strip(),
            "subject_code": str(row.get("subject_code") or "").strip(),
            "course": str(row.get("course") or "").strip(),
            "course_code": str(row.get("course_code") or "").strip(),
            "competency": str(row.get("competency") or "").strip(),
            "competency_code": str(row.get("competency_code") or "").strip(),
            "career": str(row.get("career") or "").strip(),
            "career_code": str(row.get("career_code") or "").strip(),
        }
        if not item["subject"] or not item["career"]:
            continue
        key = (
            item["subject_code"],
            item["course_code"],
            item["competency_code"],
            item["career_code"],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
