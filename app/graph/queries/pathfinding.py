from __future__ import annotations

from typing import Any, Sequence

from app.graph.models import CompetencyItem, PathfindingResult
from app.graph.neo4j_client import Neo4jClient

# A-01 tight fusion: tham số seed_* là các code do vector retrieval trả về.
# Cypher KHÔNG lọc cứng theo seed (tránh rỗng khi seed lệch ngữ cảnh).
# Career: khớp tên $career luôn thắng seed_career_codes (seed chỉ fallback khi
# tên mơ hồ). Competency: đánh dấu is_seed cho seed_competency_codes để sort/UI.
_CYPHER_BY_REL = """
MATCH (c:Career)
WITH c,
  CASE
    WHEN toLower(trim(c.career_name)) = toLower(trim($career)) THEN 0
    WHEN toLower(c.career_name) CONTAINS toLower(trim($career)) THEN 1
    WHEN toLower(trim($career)) CONTAINS toLower(c.career_name) THEN 2
    WHEN $seed_career_codes IS NOT NULL
         AND c.career_code IS NOT NULL
         AND c.career_code IN $seed_career_codes THEN 3
    ELSE 99
  END AS rank
WHERE rank < 99
WITH c, rank
ORDER BY rank, size(c.career_name)
LIMIT 1

OPTIONAL MATCH (c)-[need]->(comp)
WHERE type(need) = $rel_type

OPTIONAL MATCH (c)-[:IN_INDUSTRY]->(ind:Industry)

WITH c, ind, comp, need
ORDER BY coalesce(need.priority_group, 999) ASC, coalesce(comp.item_name, '')

WITH c, ind,
  collect({
    name: coalesce(comp.item_name, comp.item_code),
    code: comp.item_code,
    kind: head([lbl IN labels(comp) WHERE NOT lbl IN ['CompetencyType'] | lbl]),
    priority: need.priority_group,
    is_seed: (
      $seed_competency_codes IS NOT NULL
      AND comp.item_code IS NOT NULL
      AND comp.item_code IN $seed_competency_codes
    )
  }) AS raw_skills

RETURN c.career_name AS career_name,
       c.career_code AS career_code,
       ind.name AS industry,
       [s IN raw_skills WHERE s.name IS NOT NULL] AS skills
"""

_CYPHER = """
MATCH (c:Career)
WITH c,
  CASE
    WHEN toLower(trim(c.career_name)) = toLower(trim($career)) THEN 0
    WHEN toLower(c.career_name) CONTAINS toLower(trim($career)) THEN 1
    WHEN toLower(trim($career)) CONTAINS toLower(c.career_name) THEN 2
    WHEN $seed_career_codes IS NOT NULL
         AND c.career_code IS NOT NULL
         AND c.career_code IN $seed_career_codes THEN 3
    ELSE 99
  END AS rank
WHERE rank < 99
WITH c, rank
ORDER BY rank, size(c.career_name)
LIMIT 1

OPTIONAL MATCH (c)-[need]->(comp)
WHERE type(need) STARTS WITH 'NEED_'

OPTIONAL MATCH (c)-[:IN_INDUSTRY]->(ind:Industry)

WITH c, ind, comp, need
ORDER BY coalesce(need.priority_group, 999) ASC, coalesce(comp.item_name, '')

WITH c, ind,
  collect({
    name: coalesce(comp.item_name, comp.item_code),
    code: comp.item_code,
    kind: head([lbl IN labels(comp) WHERE NOT lbl IN ['CompetencyType'] | lbl]),
    priority: need.priority_group,
    is_seed: (
      $seed_competency_codes IS NOT NULL
      AND comp.item_code IS NOT NULL
      AND comp.item_code IN $seed_competency_codes
    )
  }) AS raw_skills

RETURN c.career_name AS career_name,
       c.career_code AS career_code,
       ind.name AS industry,
       [s IN raw_skills WHERE s.name IS NOT NULL] AS skills
"""


def _normalize_seed(seed: Sequence[str] | None) -> list[str] | None:
    if not seed:
        return None
    cleaned = [str(x).strip() for x in seed if x is not None and str(x).strip()]
    return cleaned or None


def fetch_pathfinding_by_type(
    client: Neo4jClient,
    career: str,
    rel_type: str,
    *,
    seed_career_codes: Sequence[str] | None = None,
    seed_competency_codes: Sequence[str] | None = None,
) -> PathfindingResult:
    """Pathfinding scoped to one NEED_* relationship type (e.g. NEED_LANG)."""
    name = (career or "").strip()
    rel = (rel_type or "").strip()
    if not name:
        return PathfindingResult(
            found=False,
            error="Chưa có tên nghề (career). Bạn muốn hướng tới nghề IT nào?",
        )
    if not rel:
        return PathfindingResult(found=False, error="Thiếu loại quan hệ NEED_* (rel_type).")

    if not client.available:
        return PathfindingResult(
            found=False,
            error="Không kết nối Neo4j. Kiểm tra docker compose và scripts/ingest.py.",
        )

    try:
        with client.session() as session:
            row = session.run(
                _CYPHER_BY_REL,
                career=name,
                rel_type=rel,
                seed_career_codes=_normalize_seed(seed_career_codes),
                seed_competency_codes=_normalize_seed(seed_competency_codes),
            ).single()
    except Exception as exc:
        return PathfindingResult(found=False, error=f"Lỗi truy vấn Neo4j: {exc}")

    if not row or not row.get("career_name"):
        return PathfindingResult(
            found=False,
            error=f"Không tìm thấy nghề «{name}» trong graph. Thử tên khác hoặc kiểm tra dữ liệu đã ingest.",
        )

    competencies = _parse_skills(row.get("skills") or [])
    return PathfindingResult(
        found=True,
        career_name=row.get("career_name"),
        career_code=row.get("career_code"),
        industry=row.get("industry"),
        competencies=competencies,
        error=None if competencies else f"Nghề «{name}» không có yêu cầu {rel} trong graph.",
    )


def fetch_pathfinding(
    client: Neo4jClient,
    career: str,
    *,
    seed_career_codes: Sequence[str] | None = None,
    seed_competency_codes: Sequence[str] | None = None,
) -> PathfindingResult:
    name = (career or "").strip()
    if not name:
        return PathfindingResult(
            found=False,
            error="Chưa có tên nghề (career). Bạn muốn hướng tới nghề IT nào?",
        )

    if not client.available:
        return PathfindingResult(
            found=False,
            error="Không kết nối Neo4j. Kiểm tra docker compose và scripts/ingest.py.",
        )

    try:
        with client.session() as session:
            row = session.run(
                _CYPHER,
                career=name,
                seed_career_codes=_normalize_seed(seed_career_codes),
                seed_competency_codes=_normalize_seed(seed_competency_codes),
            ).single()
    except Exception as exc:
        return PathfindingResult(found=False, error=f"Lỗi truy vấn Neo4j: {exc}")

    if not row or not row.get("career_name"):
        return PathfindingResult(
            found=False,
            error=f"Không tìm thấy nghề «{name}» trong graph. Thử tên khác hoặc kiểm tra dữ liệu đã ingest.",
        )

    competencies = _parse_skills(row.get("skills") or [])
    if not competencies:
        return PathfindingResult(
            found=True,
            career_name=row.get("career_name"),
            career_code=row.get("career_code"),
            industry=row.get("industry"),
            competencies=[],
            error="Đã tìm thấy nghề nhưng chưa có kỹ năng (NEED_*) liên kết trong graph.",
        )

    return PathfindingResult(
        found=True,
        career_name=row.get("career_name"),
        career_code=row.get("career_code"),
        industry=row.get("industry"),
        competencies=competencies,
    )


def _parse_skills(raw: list[dict[str, Any]]) -> list[CompetencyItem]:
    items: list[CompetencyItem] = []
    seen: set[tuple[str, str]] = set()
    for sk in raw:
        if not sk:
            continue
        comp_name = str(sk.get("name") or "").strip()
        if not comp_name:
            continue
        kind = str(sk.get("kind") or "Competency")
        key = (kind, comp_name.lower())
        if key in seen:
            continue
        seen.add(key)
        priority = sk.get("priority")
        if priority is not None:
            try:
                priority = int(priority)
            except (TypeError, ValueError):
                priority = None
        code_val = sk.get("code")
        code = str(code_val).strip() if code_val is not None else None
        items.append(
            CompetencyItem(
                name=comp_name,
                kind=kind,
                priority=priority,
                code=code or None,
                is_seed=bool(sk.get("is_seed")),
            )
        )
    # C-01: priority_group ASC (nhóm nhỏ = cốt lõi), seed boost (A-01), rồi kind/name.
    kind_order = [
        "ProgrammingLanguage",
        "Framework",
        "Platform",
        "Tool",
        "Knowledge",
        "Softskill",
        "Certification",
    ]

    def _sort_key(item: CompetencyItem) -> tuple:
        kind_idx = kind_order.index(item.kind) if item.kind in kind_order else 99
        return (
            0 if item.is_seed else 1,
            item.priority if item.priority is not None else 999,
            kind_idx,
            item.name,
        )

    items.sort(key=_sort_key)
    return items
