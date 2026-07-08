from __future__ import annotations

import re
from typing import Any, Sequence

from rapidfuzz import fuzz, process

from app.core.config import settings
from app.graph.models import CourseItem, CourseRecResult
from app.graph.neo4j_client import Neo4jClient
from app.graph.course_rank import course_item_sort_key
from app.graph.queries.competency_relation import fetch_built_on_prerequisites

# A-01 tight fusion: $seed_course_codes (nullable) chỉ dùng để gắn flag is_seed
# cho course trùng, không phải filter cứng — tránh rỗng khi seed lệch ngữ cảnh.
_CYPHER_BY_CODE = """
MATCH (comp {item_code: $item_code})
WHERE any(lbl IN labels(comp) WHERE lbl IN $labels)
MATCH (course:Course)-[teach]->(comp)
WHERE type(teach) STARTS WITH 'TEACH_'
OPTIONAL MATCH (course)-[:PROVIDED_BY]->(org:Organization)
OPTIONAL MATCH (course)-[:AT_LEVEL]->(lvl:Level)
OPTIONAL MATCH (course)-[:HAS_SUBTITLE]->(sub:Subtitle)
WITH comp, course, teach, org, lvl, sub
ORDER BY coalesce(teach.coverage_level, 0) DESC, coalesce(course.course_name, '')
WITH comp,
  collect({
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
  }) AS courses
RETURN coalesce(comp.item_name, comp.item_code) AS competency_name,
       comp.item_code AS competency_code,
       head([lbl IN labels(comp) WHERE lbl IN $labels | lbl]) AS competency_kind,
       courses
"""

_CYPHER_LIST_COMPETENCIES = """
MATCH (comp)
WHERE any(lbl IN labels(comp) WHERE lbl IN $labels)
  AND comp.item_name IS NOT NULL
RETURN comp.item_code AS code,
       comp.item_name AS name,
       head([lbl IN labels(comp) WHERE lbl IN $labels | lbl]) AS kind
ORDER BY comp.item_name
"""

# Chỉ khớp khi tên competency chứa needle (hoặc trùng khớp) — không dùng needle CONTAINS "C".
_CYPHER_COURSES_MATCH = """
MATCH (comp)
WHERE any(lbl IN labels(comp) WHERE lbl IN $labels)
  AND comp.item_name IS NOT NULL
  AND (
    toLower(trim(comp.item_name)) = toLower(trim($needle))
    OR (
      size(trim($needle)) >= 2
      AND toLower(comp.item_name) CONTAINS toLower(trim($needle))
    )
  )
WITH comp
ORDER BY
  CASE WHEN toLower(trim(comp.item_name)) = toLower(trim($needle)) THEN 0 ELSE 1 END,
  size(comp.item_name) DESC
LIMIT 1
MATCH (course:Course)-[teach]->(comp)
WHERE type(teach) STARTS WITH 'TEACH_'
OPTIONAL MATCH (course)-[:PROVIDED_BY]->(org:Organization)
OPTIONAL MATCH (course)-[:AT_LEVEL]->(lvl:Level)
OPTIONAL MATCH (course)-[:HAS_SUBTITLE]->(sub:Subtitle)
WITH comp, course, teach, org, lvl, sub
ORDER BY coalesce(teach.coverage_level, 0) DESC, coalesce(course.course_name, '')
WITH comp,
  collect({
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
  }) AS courses
RETURN coalesce(comp.item_name, comp.item_code) AS competency_name,
       comp.item_code AS competency_code,
       head([lbl IN labels(comp) WHERE lbl IN $labels | lbl]) AS competency_kind,
       courses
"""

_KNOWN_TOKEN_RE = re.compile(
    r"\b(?:SQL|Python|Java(?:Script)?|React|Docker|Kubernetes|AWS|Azure|GCP|"
    r"HTML|CSS|Node\.?js|C\+\+|C#|PHP|Go|Rust|TypeScript|CBAP|PMP|Scrum|Agile)\b",
    re.IGNORECASE,
)
_ACRONYM_RE = re.compile(r"\b[A-Z]{3,}\b")
_WORD_RE = re.compile(r"[\w#+]{2,}", re.UNICODE)


def _competency_search_terms(needle: str) -> list[str]:
    """Tách token kỹ năng/chứng chỉ từ câu hỏi dài (tránh khớp nhầm chữ «c» trong CBAP)."""
    text = (needle or "").strip()
    if not text:
        return []

    tokens: list[str] = []
    seen: set[str] = set()

    def add(t: str) -> None:
        t = t.strip()
        if not t:
            return
        key = t.lower()
        if key not in seen:
            seen.add(key)
            tokens.append(t)

    for m in _KNOWN_TOKEN_RE.finditer(text):
        add(m.group(0))
    for m in _ACRONYM_RE.finditer(text):
        add(m.group(0))
    if not tokens and len(text) <= 64:
        add(text)
    elif not tokens:
        for w in sorted(_WORD_RE.findall(text), key=len, reverse=True):
            if len(w) >= 3:
                add(w)
                if len(tokens) >= 3:
                    break
    return tokens


def _is_spurious_short_match(needle: str, competency_name: str) -> bool:
    """Chặn CBAP → C, SQL course → C, v.v."""
    n = needle.strip().lower()
    c = competency_name.strip().lower()
    if not n or not c:
        return True
    if n == c:
        return False
    if len(c) > 2:
        return False
    # Tên competency 1–2 ký tự: chỉ chấp nhận nếu người dùng hỏi đúng token đó (word boundary).
    return re.search(rf"\b{re.escape(c)}\b", n, re.IGNORECASE) is None


_CYPHER_COURSES_BY_REL = """
MATCH (comp)
WHERE any(lbl IN labels(comp) WHERE lbl IN $labels)
  AND comp.item_name IS NOT NULL
  AND (
    toLower(trim(comp.item_name)) = toLower(trim($needle))
    OR (
      size(trim($needle)) >= 2
      AND toLower(comp.item_name) CONTAINS toLower(trim($needle))
    )
  )
WITH comp
ORDER BY
  CASE WHEN toLower(trim(comp.item_name)) = toLower(trim($needle)) THEN 0 ELSE 1 END,
  size(comp.item_name) DESC
LIMIT 1
MATCH (course:Course)-[teach]->(comp)
WHERE type(teach) = $rel_type
OPTIONAL MATCH (course)-[:PROVIDED_BY]->(org:Organization)
OPTIONAL MATCH (course)-[:AT_LEVEL]->(lvl:Level)
OPTIONAL MATCH (course)-[:HAS_SUBTITLE]->(sub:Subtitle)
WITH comp, course, teach, org, lvl, sub
ORDER BY coalesce(teach.coverage_level, 0) DESC, coalesce(course.course_name, '')
WITH comp,
  collect({
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
  }) AS courses
RETURN coalesce(comp.item_name, comp.item_code) AS competency_name,
       comp.item_code AS competency_code,
       head([lbl IN labels(comp) WHERE lbl IN $labels | lbl]) AS competency_kind,
       courses
"""

def _normalize_seed(seed: Sequence[str] | None) -> list[str] | None:
    if not seed:
        return None
    cleaned = [str(x).strip() for x in seed if x is not None and str(x).strip()]
    return cleaned or None


def fetch_courses_by_type(
    client: Neo4jClient,
    competency: str,
    rel_type: str,
    *,
    seed_course_codes: Sequence[str] | None = None,
) -> CourseRecResult:
    """Course recommendations filtered to one TEACH_* relationship type."""
    needle = (competency or "").strip()
    rel = (rel_type or "").strip()
    if not needle:
        return CourseRecResult(
            found=False,
            error="Chưa có tên kỹ năng (competency). Bạn muốn học công nghệ/kỹ năng nào?",
        )
    if not rel:
        return CourseRecResult(found=False, error="Thiếu loại quan hệ TEACH_* (rel_type).")

    if not client.available:
        return CourseRecResult(
            found=False,
            error="Không kết nối Neo4j. Kiểm tra docker compose và scripts/ingest.py.",
        )

    labels = list(client.competency_labels())
    search_terms = _competency_search_terms(needle)
    seed_codes = _normalize_seed(seed_course_codes)

    try:
        with client.session() as session:
            row = None
            for term in search_terms:
                row = session.run(
                    _CYPHER_COURSES_BY_REL,
                    needle=term,
                    labels=labels,
                    rel_type=rel,
                    seed_course_codes=seed_codes,
                ).single()
                if row and row.get("competency_name"):
                    name = str(row.get("competency_name") or "")
                    if not _is_spurious_short_match(term, name):
                        break
                    row = None

            if not row or not row.get("competency_name"):
                display = search_terms[0] if search_terms else needle
                return CourseRecResult(
                    found=False,
                    error=f"Không tìm thấy kỹ năng «{display}» với khóa học {rel} trong graph.",
                )

            courses = _parse_courses(row.get("courses") or [])
            if not courses:
                item_code = str(row.get("competency_code") or "").strip()
                if item_code:
                    fallback = _fallback_via_built_on(
                        client,
                        session,
                        labels=labels,
                        item_code=item_code,
                        comp_name=str(row.get("competency_name") or ""),
                        comp_kind=row.get("competency_kind"),
                        seed_codes=seed_codes,
                    )
                    if fallback:
                        return fallback
                return CourseRecResult(
                    found=True,
                    competency_name=row.get("competency_name"),
                    competency_kind=row.get("competency_kind"),
                    competency_code=item_code or None,
                    courses=[],
                    error=f"Đã tìm thấy kỹ năng nhưng chưa có khóa học ({rel}) liên kết.",
                )

            return CourseRecResult(
                found=True,
                competency_name=row.get("competency_name"),
                competency_kind=row.get("competency_kind"),
                competency_code=str(row.get("competency_code") or "") or None,
                courses=courses,
            )
    except Exception as exc:
        return CourseRecResult(found=False, error=f"Lỗi truy vấn Neo4j: {exc}")


def fetch_course_recommendations(
    client: Neo4jClient,
    competency: str,
    *,
    seed_course_codes: Sequence[str] | None = None,
) -> CourseRecResult:
    needle = (competency or "").strip()
    if not needle:
        return CourseRecResult(
            found=False,
            error="Chưa có tên kỹ năng (competency). Bạn muốn học công nghệ/kỹ năng nào?",
        )

    if not client.available:
        return CourseRecResult(
            found=False,
            error="Không kết nối Neo4j. Kiểm tra docker compose và scripts/ingest.py.",
        )

    labels = list(client.competency_labels())
    search_terms = _competency_search_terms(needle)
    seed_codes = _normalize_seed(seed_course_codes)

    try:
        with client.session() as session:
            row = None
            for term in search_terms:
                row = session.run(
                    _CYPHER_COURSES_MATCH,
                    needle=term,
                    labels=labels,
                    seed_course_codes=seed_codes,
                ).single()
                if row and row.get("competency_name"):
                    name = str(row.get("competency_name") or "")
                    if not _is_spurious_short_match(term, name):
                        break
                    row = None

            if not row or not row.get("competency_name"):
                row = _resolve_via_fuzzy(
                    session,
                    search_terms or [needle],
                    labels,
                    seed_course_codes=seed_codes,
                )

            if not row or not row.get("competency_name"):
                display = search_terms[0] if search_terms else needle
                return CourseRecResult(
                    found=False,
                    error=f"Không tìm thấy kỹ năng «{display}» trong graph.",
                )

            return _finalize_course_rec(
                client, session, row, labels=labels, seed_codes=seed_codes
            )
    except Exception as exc:
        return CourseRecResult(found=False, error=f"Lỗi truy vấn Neo4j: {exc}")


def _resolve_via_fuzzy(
    session,
    needles: list[str],
    labels: list[str],
    *,
    seed_course_codes: list[str] | None = None,
) -> Any:
    rows = list(session.run(_CYPHER_LIST_COMPETENCIES, labels=labels))
    if not rows:
        return None

    names = [r["name"] for r in rows if r.get("name")]
    code_by_name = {r["name"]: r["code"] for r in rows if r.get("name")}

    for needle in needles:
        match = process.extractOne(
            needle,
            names,
            scorer=fuzz.WRatio,
            score_cutoff=settings.router_career_fuzzy_threshold,
        )
        if not match:
            continue
        matched_name = match[0]
        if _is_spurious_short_match(needle, matched_name):
            continue
        code = code_by_name.get(matched_name)
        if not code:
            continue
        row = session.run(
            _CYPHER_BY_CODE,
            item_code=code,
            labels=labels,
            seed_course_codes=seed_course_codes,
        ).single()
        if row and row.get("competency_name"):
            return row
    return None


def _parse_courses(raw: list[dict[str, Any]]) -> list[CourseItem]:
    items: list[CourseItem] = []
    seen: set[str] = set()
    for c in raw:
        if not c:
            continue
        name = str(c.get("course_name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        cov = c.get("coverage_level")
        if cov is not None:
            try:
                cov = int(cov)
            except (TypeError, ValueError):
                cov = None
        items.append(
            CourseItem(
                course_name=name,
                course_code=c.get("course_code"),
                organization=c.get("organization"),
                level=c.get("level"),
                subtitle=c.get("subtitle"),
                url=c.get("url"),
                duration_hours=c.get("duration_hours"),
                coverage_level=cov,
                is_seed=bool(c.get("is_seed")),
            )
        )
    items.sort(
        key=lambda x: course_item_sort_key(
            url=x.url,
            coverage_level=x.coverage_level,
            is_seed=x.is_seed,
            course_name=x.course_name,
        )
    )
    return items


def _fallback_via_built_on(
    client: Neo4jClient,
    session,
    *,
    labels: list[str],
    item_code: str,
    comp_name: str,
    comp_kind: str | None,
    seed_codes: list[str] | None,
) -> CourseRecResult | None:
    prereqs = fetch_built_on_prerequisites(client, item_code)
    if not prereqs:
        return None

    via_blocks: list[dict] = []
    all_courses: list[CourseItem] = []
    for prereq in prereqs:
        prow = session.run(
            _CYPHER_BY_CODE,
            item_code=prereq["code"],
            labels=labels,
            seed_course_codes=seed_codes,
        ).single()
        pcourses = _parse_courses(prow.get("courses") or []) if prow else []
        if pcourses:
            via_blocks.append(
                {
                    "code": prereq["code"],
                    "name": prereq["name"],
                    "relation": "BUILT_ON",
                    "note": prereq.get("note"),
                    "courses": [c.model_dump() for c in pcourses],
                }
            )
            all_courses.extend(pcourses)

    if not via_blocks:
        return None

    note = prereq_names = ", ".join(p["name"] for p in prereqs)
    return CourseRecResult(
        found=True,
        competency_name=comp_name,
        competency_kind=comp_kind,
        competency_code=item_code,
        courses=all_courses[:8],
        via_prerequisites=via_blocks,
        fallback_reason="no_direct_course",
        error=(
            f"Chưa có khóa học trực tiếp cho «{comp_name}»; "
            f"gợi ý khóa nền tảng ({note}) qua quan hệ BUILT_ON."
        ),
    )


def _finalize_course_rec(
    client: Neo4jClient,
    session,
    row: Any,
    *,
    labels: list[str],
    seed_codes: list[str] | None,
) -> CourseRecResult:
    comp_name = row.get("competency_name")
    comp_kind = row.get("competency_kind")
    item_code = str(row.get("competency_code") or "").strip()
    courses = _parse_courses(row.get("courses") or [])

    if courses:
        return CourseRecResult(
            found=True,
            competency_name=comp_name,
            competency_kind=comp_kind,
            competency_code=item_code or None,
            courses=courses,
        )

    if item_code:
        fallback = _fallback_via_built_on(
            client,
            session,
            labels=labels,
            item_code=item_code,
            comp_name=str(comp_name or ""),
            comp_kind=comp_kind,
            seed_codes=seed_codes,
        )
        if fallback:
            return fallback

    return CourseRecResult(
        found=True,
        competency_name=comp_name,
        competency_kind=comp_kind,
        competency_code=item_code or None,
        courses=[],
        error="Đã tìm thấy kỹ năng nhưng chưa có khóa học (TEACH_*) liên kết.",
    )
