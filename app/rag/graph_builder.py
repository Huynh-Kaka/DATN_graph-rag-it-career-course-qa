from __future__ import annotations

from typing import Any, List

from neo4j import GraphDatabase, Driver

from app.core.config import settings

_CYPHER_CONTEXT = """
MATCH (c:Career)
WITH c,
  CASE
    WHEN toLower(trim(c.career_name)) = toLower(trim($role)) THEN 0
    WHEN toLower(c.career_name) CONTAINS toLower($role) THEN 1
    WHEN toLower($role) CONTAINS toLower(c.career_name) THEN 2
    ELSE 99
  END AS rank
WHERE rank < 99
WITH c, rank
ORDER BY rank, size(c.career_name)
LIMIT 1

OPTIONAL MATCH (c)-[need]->(comp)
WHERE type(need) STARTS WITH 'NEED_'

WITH c,
  collect(DISTINCT {
    name: coalesce(comp.item_name, comp.type_name, comp.name, comp.item_code),
    kind: head([lbl IN labels(comp) WHERE NOT lbl IN ['CompetencyType'] | lbl]),
    priority: need.priority_group
  }) AS skills

OPTIONAL MATCH (c)-[need2]->(comp2)
WHERE type(need2) STARTS WITH 'NEED_'
OPTIONAL MATCH (course:Course)-[teach]->(comp2)
WHERE type(teach) STARTS WITH 'TEACH_'

WITH c, skills,
  collect(DISTINCT coalesce(course.course_name, course.course_code)) AS course_list

OPTIONAL MATCH (c)-[:IN_INDUSTRY]->(ind:Industry)

RETURN c.career_name AS career_name,
       c.career_code AS career_code,
       ind.name AS industry,
       [s IN skills WHERE s.name IS NOT NULL] AS skills,
       [x IN course_list WHERE x IS NOT NULL] AS courses
"""

_CYPHER_LIST_CAREERS = """
MATCH (c:Career)
RETURN c.career_name AS name
ORDER BY c.career_name
LIMIT $limit
"""


class GraphContextBuilder:
    """Truy vấn Neo4j theo vai trò mục tiêu; fallback nếu không kết nối được DB."""

    def __init__(self) -> None:
        self._driver: Driver | None = None
        try:
            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
            self._driver.verify_connectivity()
        except Exception:
            if self._driver is not None:
                self._driver.close()
            self._driver = None

    def get_graph_context(self, target_role: str = "", *, top_skills: int = 12) -> List[str]:
        role = (target_role or "").strip()
        if not role:
            return ["Chưa chỉ định vai trò mục tiêu."]

        if self._driver is None:
            return _stub_context(
                role,
                note="Không kết nối Neo4j. Chạy: docker compose up -d neo4j "
                "và python scripts/ingest.py --xlsx-path \"data/bộ dữ liệu.xlsx\"",
            )

        try:
            with self._driver.session() as session:
                row = session.run(_CYPHER_CONTEXT, role=role).single()
                if row:
                    lines = _format_graph_row(row, top_skills=top_skills)
                    if lines:
                        return lines

                suggestions = [
                    r["name"]
                    for r in session.run(_CYPHER_LIST_CAREERS, limit=8)
                    if r.get("name")
                ]
                if suggestions:
                    return [
                        f"Không tìm thấy nghề khớp «{role}» trong graph.",
                        "Gợi ý tên nghề có trong DB: " + ", ".join(suggestions),
                    ]
                return [
                    f"Graph Neo4j trống hoặc chưa có Career khớp «{role}».",
                    "Chạy scripts/ingest.py để nạp dữ liệu Excel.",
                ]
        except Exception as exc:
            return _stub_context(role, note=f"Lỗi truy vấn Neo4j: {exc}")

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None


def _format_graph_row(row: Any, *, top_skills: int) -> List[str]:
    lines: List[str] = []
    career = row.get("career_name") or row.get("career_code")
    if career:
        code = row.get("career_code")
        lines.append(f"Nghề (từ graph): {career}" + (f" [{code}]" if code else ""))
    if row.get("industry"):
        lines.append(f"Ngành: {row['industry']}")

    by_kind: dict[str, list[str]] = {}
    for sk in row.get("skills") or []:
        if not sk or not sk.get("name"):
            continue
        kind = sk.get("kind") or "Competency"
        label = str(sk["name"])
        if sk.get("priority") is not None:
            label += f" (ưu tiên {sk['priority']})"
        by_kind.setdefault(kind, []).append(label)

    for kind, names in sorted(by_kind.items()):
        shown = names[:top_skills]
        lines.append(f"{kind}: " + "; ".join(shown))
        if len(names) > len(shown):
            lines.append(f"  … và {len(names) - len(shown)} mục {kind} khác")

    courses = (row.get("courses") or [])[:8]
    if courses:
        lines.append("Khóa học liên quan (TEACH_*): " + "; ".join(str(c) for c in courses))

    return lines


def _stub_context(role: str, *, note: str) -> List[str]:
    return [
        note,
        f"(Dữ liệu mẫu tạm cho «{role}»)",
        f"Nền tảng chuyên môn cho {role}",
        "Làm việc nhóm và giao tiếp kỹ thuật",
    ]
