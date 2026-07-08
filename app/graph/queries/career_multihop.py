from __future__ import annotations

from typing import Any, Sequence

from app.graph.models import CareerSkillCoursesResult, CourseItem, SkillCoursesBlock
from app.graph.neo4j_client import Neo4jClient
from app.graph.course_rank import course_raw_sort_key
from app.graph.queries.course_rec import _parse_courses, fetch_course_recommendations

# A-02: Multi-hop thật — Career -[NEED_*]-> Competency <-[TEACH_*]- Course
# Gộp pathfinding + course_rec thành một round-trip Neo4j.
_CYPHER_MULTIHOP = """
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

MATCH (c)-[need]->(comp)
WHERE type(need) STARTS WITH 'NEED_'
  AND ($need_rel IS NULL OR type(need) = $need_rel)
  AND comp.item_name IS NOT NULL
  AND toLower(trim(comp.item_name)) IN $skill_names_lower

MATCH (course:Course)-[teach]->(comp)
WHERE type(teach) STARTS WITH 'TEACH_'
  AND ($teach_rel IS NULL OR type(teach) = $teach_rel)

OPTIONAL MATCH (course)-[:PROVIDED_BY]->(org:Organization)
OPTIONAL MATCH (course)-[:AT_LEVEL]->(lvl:Level)
OPTIONAL MATCH (course)-[:HAS_SUBTITLE]->(sub:Subtitle)

WITH c, comp, need, teach,
  collect(DISTINCT {
    course_name: coalesce(course.course_name, course.course_code),
    course_code: course.course_code,
    organization: org.org_name,
    level: lvl.level_name,
    subtitle: sub.subtitle_name,
    url: course.url,
    duration_hours: course.duration_hours,
    coverage_level: teach.coverage_level,
    is_seed: (
      $seed_course_codes IS NOT NULL
      AND course.course_code IS NOT NULL
      AND course.course_code IN $seed_course_codes
    )
  }) AS raw_courses

RETURN c.career_name AS career_name,
       c.career_code AS career_code,
       coalesce(comp.item_name, comp.item_code) AS competency_name,
       comp.item_code AS competency_code,
       head([lbl IN labels(comp) WHERE lbl IN $labels | lbl]) AS competency_kind,
       need.priority_group AS priority,
       [x IN raw_courses WHERE x.course_name IS NOT NULL] AS courses
ORDER BY priority ASC
"""


def _normalize_seed(seed: Sequence[str] | None) -> list[str] | None:
    if not seed:
        return None
    cleaned = [str(x).strip() for x in seed if x is not None and str(x).strip()]
    return cleaned or None


def _teach_need_pair(rel_type: str | None) -> tuple[str | None, str | None]:
    """Map TEACH_* ↔ NEED_* khi caller truyền rel typed."""
    if not rel_type:
        return None, None
    rel = rel_type.strip()
    if rel.startswith("TEACH_"):
        return "NEED_" + rel[6:], rel
    if rel.startswith("NEED_"):
        return rel, "TEACH_" + rel[5:]
    return None, None


def _sort_courses(raw: list[dict[str, Any]]) -> list[CourseItem]:
    """Ưu tiên course.url cụ thể, rồi coverage_level, rồi seed."""
    ranked = sorted(raw, key=course_raw_sort_key)
    return _parse_courses(ranked)


def fetch_courses_for_career_skills(
    client: Neo4jClient,
    career: str,
    skill_names: list[str],
    *,
    rel_type: str | None = None,
    max_per_skill: int = 4,
    seed_career_codes: Sequence[str] | None = None,
    seed_course_codes: Sequence[str] | None = None,
) -> CareerSkillCoursesResult:
    """
    Multi-hop: lấy khóa học cho nhiều competency của một nghề trong 1 query.
    """
    name = (career or "").strip()
    skills = [str(s).strip() for s in (skill_names or []) if str(s).strip()]
    if not name:
        return CareerSkillCoursesResult(
            found=False,
            error="Chưa có tên nghề (career).",
        )
    if not skills:
        return CareerSkillCoursesResult(found=False, error="Danh sách kỹ năng trống.")

    if not client.available:
        return CareerSkillCoursesResult(
            found=False,
            error="Không kết nối Neo4j. Kiểm tra docker compose và scripts/ingest.py.",
        )

    need_rel, teach_rel = _teach_need_pair(rel_type)
    labels = list(client.competency_labels())
    skill_names_lower = [s.lower() for s in skills]

    try:
        with client.session() as session:
            rows = list(
                session.run(
                    _CYPHER_MULTIHOP,
                    career=name,
                    skill_names_lower=skill_names_lower,
                    labels=labels,
                    need_rel=need_rel,
                    teach_rel=teach_rel,
                    seed_career_codes=_normalize_seed(seed_career_codes),
                    seed_course_codes=_normalize_seed(seed_course_codes),
                )
            )
    except Exception as exc:
        return CareerSkillCoursesResult(found=False, error=f"Lỗi truy vấn Neo4j: {exc}")

    if not rows:
        return CareerSkillCoursesResult(
            found=False,
            error=f"Không tìm thấy khóa học multi-hop cho nghề «{name}».",
        )

    career_name = rows[0].get("career_name")
    career_code = rows[0].get("career_code")
    blocks: list[SkillCoursesBlock] = []
    seen_skills: set[str] = set()

    # Giữ thứ tự skill_names người gọi yêu cầu (roadmap ưu tiên gap list).
    row_by_skill = {
        str(r.get("competency_name") or "").strip().lower(): r for r in rows
    }

    for skill in skills:
        row = row_by_skill.get(skill.lower())
        if not row:
            continue
        comp_name = str(row.get("competency_name") or skill)
        key = comp_name.lower()
        if key in seen_skills:
            continue
        seen_skills.add(key)

        courses = _sort_courses(row.get("courses") or [])[: max(1, max_per_skill)]
        if not courses:
            comp_code = str(row.get("competency_code") or "").strip()
            if comp_code or comp_name:
                fb = fetch_course_recommendations(
                    client,
                    comp_name,
                    seed_course_codes=_normalize_seed(seed_course_codes),
                )
                if fb.found and fb.courses:
                    courses = fb.courses[: max(1, max_per_skill)]

        if not courses:
            continue

        priority = row.get("priority")
        if priority is not None:
            try:
                priority = int(priority)
            except (TypeError, ValueError):
                priority = None

        blocks.append(
            SkillCoursesBlock(
                competency_name=comp_name,
                competency_kind=row.get("competency_kind"),
                competency_code=row.get("competency_code"),
                priority=priority,
                courses=courses,
            )
        )

    if not blocks:
        return CareerSkillCoursesResult(
            found=False,
            career_name=career_name,
            career_code=career_code,
            error=f"Đã khớp nghề «{name}» nhưng không có khóa TEACH_* cho các kỹ năng yêu cầu.",
        )

    return CareerSkillCoursesResult(
        found=True,
        career_name=career_name,
        career_code=career_code,
        blocks=blocks,
    )
