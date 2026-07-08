"""Gợi ý khóa học theo danh sách kỹ năng thiếu (multi-hop Neo4j)."""

from __future__ import annotations

import re
from typing import Any

from app.advice.schema import _coerce_courses, is_generic_site_url
from app.graph.repository import GraphRepository
from app.response.structured import course_item_to_chip, priority_badge
from app.session.competency_types import need_rel_for_type

_DEFAULT_MAX_PER_SKILL = 4
_DEFAULT_MAX_PER_MONTH = 3


def advice_course_from_chip(chip: dict[str, Any]) -> dict[str, Any]:
    title = (chip.get("title") or chip.get("course_name") or "").strip()
    platform = (chip.get("organization") or chip.get("platform") or "").strip()
    out: dict[str, Any] = {
        "title": title or "Khóa học",
        "platform": platform or "Gợi ý chung",
    }
    url = str(chip.get("url") or "").strip()
    if url and not is_generic_site_url(url):
        out["url"] = url
    return out


def _collect_course_lookup_skills(
    missing_skills: list[str],
    roadmap: list[dict[str, Any]],
) -> list[str]:
    """Gom kỹ năng thiếu + chủ đề từng tháng để truy vấn Neo4j (vd. Docker trong topics)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in list(missing_skills or []):
        label = str(raw).strip()
        key = label.lower()
        if label and key not in seen:
            seen.add(key)
            out.append(label)
    for item in roadmap or []:
        for topic in item.get("topics") or []:
            label = str(topic).strip()
            key = label.lower()
            if label and key not in seen:
                seen.add(key)
                out.append(label)
    return out


def _graph_course_index(courses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for course in courses:
        title = (course.get("title") or "").strip().lower()
        if title and title not in index:
            index[title] = course
    return index


def _find_graph_course(title: str, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    key = (title or "").strip().lower()
    if not key:
        return None
    if key in index:
        return index[key]
    for gtitle, course in index.items():
        if gtitle in key or key in gtitle:
            return course
    return None


def _topic_matches_skill(topic: str, skill_key: str) -> bool:
    if not topic or not skill_key:
        return False
    if skill_key in topic or topic in skill_key:
        return True
    tokens = {t for t in re.split(r"[\s/&,]+", topic) if t}
    return skill_key in tokens


def _overlay_graph_urls(
    courses: list[dict[str, Any]],
    graph_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Thay URL trang web bằng course.url từ graph khi khớp tên khóa."""
    out: list[dict[str, Any]] = []
    for item in courses:
        title = (item.get("title") or "").strip()
        graph_match = _find_graph_course(title, graph_index)
        if graph_match and graph_match.get("url"):
            merged = dict(item)
            merged["title"] = graph_match.get("title") or title
            merged["platform"] = (
                graph_match.get("platform")
                or item.get("platform")
                or "Gợi ý chung"
            )
            merged["url"] = graph_match["url"]
            out.append(merged)
            continue
        cleaned = dict(item)
        if is_generic_site_url(cleaned.get("url")):
            cleaned.pop("url", None)
        out.append(cleaned)
    return out


def _resolve_month_courses_from_graph(
    topics: list[str],
    skill_courses: dict[str, list[dict[str, Any]]],
    targets: list[str],
    month_idx: int,
    pool: list[dict[str, Any]],
    pool_cursor: int,
    *,
    max_per_month: int,
) -> tuple[list[dict[str, Any]], int]:
    """Ưu tiên khóa học graph khớp chủ đề tháng; fallback theo thứ tự kỹ năng thiếu."""
    month_courses: list[dict[str, Any]] = []
    used: set[str] = set()

    for topic in topics:
        for skill_key, courses in skill_courses.items():
            if not _topic_matches_skill(topic, skill_key):
                continue
            for course in courses:
                title_key = course["title"].lower()
                if title_key in used:
                    continue
                month_courses.append(course)
                used.add(title_key)
                if len(month_courses) >= max_per_month:
                    return month_courses, pool_cursor
        if len(month_courses) >= max_per_month:
            break

    if not month_courses and targets:
        skill = targets[min(month_idx, len(targets) - 1)]
        for course in skill_courses.get(skill.lower(), []):
            title_key = course["title"].lower()
            if title_key in used:
                continue
            month_courses.append(course)
            used.add(title_key)
            if len(month_courses) >= max_per_month:
                break

    while len(month_courses) < max_per_month and pool_cursor < len(pool):
        course = pool[pool_cursor]
        pool_cursor += 1
        title_key = course["title"].lower()
        if title_key in used:
            continue
        month_courses.append(course)
        used.add(title_key)

    return month_courses, pool_cursor


def enrich_advice_roadmap(
    roadmap: list[dict[str, Any]],
    missing_skills: list[str],
    graph: GraphRepository,
    career: str,
    *,
    max_per_month: int = _DEFAULT_MAX_PER_MONTH,
    max_per_skill: int = _DEFAULT_MAX_PER_SKILL,
) -> list[dict[str, Any]]:
    """Bổ sung khóa học Neo4j — graph-first theo chủ đề tháng, không giữ LLM hallucination."""
    if not roadmap:
        return roadmap

    targets = _collect_course_lookup_skills(missing_skills, roadmap)
    skill_courses: dict[str, list[dict[str, Any]]] = {}
    pool: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    if targets and (career or "").strip():
        batch = graph.courses_for_career_skills(
            career,
            targets,
            max_per_skill=max_per_skill,
        )
        for block in batch.blocks:
            chips = [
                advice_course_from_chip(course_item_to_chip(c.model_dump()))
                for c in block.courses[:max_per_skill]
            ]
            key = (block.competency_name or "").strip().lower()
            if key:
                skill_courses[key] = chips
            for course in chips:
                title_key = course["title"].lower()
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                pool.append(course)

    enriched: list[dict[str, Any]] = []
    pool_cursor = 0
    graph_index = _graph_course_index(pool)

    for idx, item in enumerate(roadmap):
        entry = dict(item)
        topics = [str(t).strip().lower() for t in (entry.get("topics") or []) if t]

        month_courses, pool_cursor = _resolve_month_courses_from_graph(
            topics,
            skill_courses,
            targets,
            idx,
            pool,
            pool_cursor,
            max_per_month=max_per_month,
        )

        if month_courses:
            entry["courses"] = month_courses[:max_per_month]
        else:
            existing = _overlay_graph_urls(
                _coerce_courses(entry.get("courses")),
                graph_index,
            )
            entry["courses"] = existing[:max_per_month]

        enriched.append(entry)

    return enriched


def enrich_advice_skills_gap(
    payload: dict[str, Any],
    graph: GraphRepository,
    career: str,
    *,
    known_skills: list[str] | None = None,
) -> dict[str, Any]:
    """Bổ sung kỹ năng mềm và chứng chỉ từ graph (NEED_SOFT / NEED_CERT)."""
    if not (career or "").strip():
        return payload

    payload = dict(payload)
    gap = dict(payload.get("skills_gap") or {})
    known = list(known_skills or [])

    for type_code, key in (("CT_SOFT", "soft_skills"), ("CT_CERT", "certifications")):
        rel = need_rel_for_type(type_code)
        if not rel:
            gap.setdefault(key, [])
            continue
        try:
            pf = graph.pathfinding_by_type(career, rel, known_skills=known)
        except Exception:
            gap.setdefault(key, [])
            continue
        if pf.found:
            gap[key] = [c.name for c in pf.skills_missing if c.name][:15]
        else:
            gap.setdefault(key, [])

    payload["skills_gap"] = gap
    return payload


def enrich_advice_payload_courses(
    payload: dict[str, Any],
    graph: GraphRepository,
    career: str,
    *,
    known_skills: list[str] | None = None,
) -> dict[str, Any]:
    """Post-process advice: skills gap (soft/cert) + khóa học graph vào roadmap."""
    from app.advice.schema import flatten_roadmap_courses, normalize_advice_payload

    payload = enrich_advice_skills_gap(
        payload, graph, career, known_skills=known_skills
    )

    roadmap = list(payload.get("roadmap") or [])
    if not roadmap:
        return normalize_advice_payload(payload, raw_response=payload.get("raw_response"))

    gap = payload.get("skills_gap") or {}
    missing = [str(x) for x in (gap.get("missing") or []) if x]
    roadmap = enrich_advice_roadmap(roadmap, missing, graph, career)

    payload = dict(payload)
    payload["roadmap"] = roadmap
    payload["recommended_courses"] = flatten_roadmap_courses(roadmap) or list(
        payload.get("recommended_courses") or []
    )
    return normalize_advice_payload(payload, raw_response=payload.get("raw_response"))


def build_courses_by_skill_blocks(
    graph: GraphRepository,
    career: str,
    skill_labels: list[str],
    *,
    max_per_skill: int = _DEFAULT_MAX_PER_SKILL,
) -> list[dict[str, Any]]:
    """Một block UI cho mỗi kỹ năng thiếu (kể cả khi graph chưa có khóa)."""
    targets = [str(s).strip() for s in (skill_labels or []) if str(s).strip()]
    if not targets or not (career or "").strip():
        return []

    batch = graph.courses_for_career_skills(
        career,
        targets,
        max_per_skill=max_per_skill,
    )
    by_skill = {b.competency_name: b for b in batch.blocks}

    blocks: list[dict[str, Any]] = []
    for skill in targets:
        block = by_skill.get(skill)
        if block is None:
            for b in batch.blocks:
                if b.competency_name.lower() == skill.lower():
                    block = b
                    break
        courses = [
            course_item_to_chip(c.model_dump())
            for c in (block.courses if block else [])[:max_per_skill]
        ]
        prio = block.priority if block else None
        blocks.append(
            {
                "skill": skill,
                "priority": prio,
                "priority_badge": priority_badge(prio),
                "found": bool(courses),
                "courses": courses,
            }
        )
    return blocks
