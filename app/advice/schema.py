"""
JSON Schema cho structured output tư vấn (Gemini response_schema / OpenAI json_schema).
"""

from __future__ import annotations

from typing import Any, TypedDict
from urllib.parse import urlparse

_GENERIC_SITE_SEGMENTS = frozenset(
    {
        "",
        "courses",
        "course",
        "learn",
        "browse",
        "catalog",
        "training",
        "certification",
        "certifications",
    }
)


def is_generic_site_url(url: str | None) -> bool:
    """True nếu URL là trang chủ nền tảng, không phải link khóa học cụ thể."""
    raw = (url or "").strip()
    if not raw:
        return True
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if not parsed.netloc:
        return True
    path = (parsed.path or "").strip("/")
    if not path:
        return True
    segments = [s for s in path.split("/") if s]
    if len(segments) == 1 and segments[0].lower() in _GENERIC_SITE_SEGMENTS:
        return True
    if len(segments) == 2 and segments[0].lower() in ("en-us", "en", "vi", "vi-vn"):
        if segments[1].lower() in _GENERIC_SITE_SEGMENTS:
            return True
    return False

ADVICE_RESULT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "skills_gap": {
            "type": "object",
            "properties": {
                "missing": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Kỹ năng còn thiếu so với mục tiêu nghề",
                },
                "weak": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Kỹ năng đã có nhưng cần củng cố",
                },
            },
            "required": ["missing", "weak"],
        },
        "roadmap": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "month": {"type": "integer"},
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "milestone": {"type": "string"},
                    "courses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "platform": {"type": "string"},
                                "url": {"type": "string"},
                            },
                            "required": ["title", "platform"],
                        },
                        "description": "1-3 khóa học cụ thể cho tháng này",
                    },
                },
                "required": ["month", "topics", "milestone"],
            },
        },
        "recommended_courses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "platform": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["title", "platform"],
            },
        },
        "estimated_months": {
            "type": "integer",
            "description": "Ước tính số tháng sẵn sàng đi làm",
        },
        "summary_vi": {
            "type": "string",
            "description": "Tóm tắt tư vấn bằng tiếng Việt, thân thiện, 2-4 đoạn",
        },
    },
    "required": [
        "skills_gap",
        "roadmap",
        "recommended_courses",
        "estimated_months",
        "summary_vi",
    ],
}


class AdvicePayload(TypedDict, total=False):
    """Canonical advisory result after normalization (LLM, cache, graph fallback)."""

    id: str
    session_id: str
    profile_id: str | None
    created_at: str
    skills_gap: dict[str, list[str]]
    roadmap: list[dict[str, Any]]
    recommended_courses: list[dict[str, Any]]
    estimated_months: int | None
    summary_vi: str
    raw_response: str


def normalize_skills_gap(gap: Any) -> dict[str, list[str]]:
    """Chuẩn hóa skills_gap từ LLM/cache về {missing, weak, soft_skills, certifications}."""
    empty = {
        "missing": [],
        "weak": [],
        "soft_skills": [],
        "certifications": [],
    }
    if isinstance(gap, list):
        return {**empty, "missing": [str(x) for x in gap if x]}
    if not isinstance(gap, dict):
        return dict(empty)
    if "missing" in gap or "weak" in gap:
        return {
            "missing": [str(x) for x in (gap.get("missing") or []) if x],
            "weak": [str(x) for x in (gap.get("weak") or []) if x],
            "soft_skills": [str(x) for x in (gap.get("soft_skills") or []) if x],
            "certifications": [str(x) for x in (gap.get("certifications") or []) if x],
        }
    missing: list[str] = []
    for key in ("mandatory", "required", "recommended"):
        missing.extend(str(x) for x in (gap.get(key) or []) if x)
    weak = [str(x) for x in (gap.get("optional") or gap.get("weak") or []) if x]
    return {
        "missing": missing,
        "weak": weak,
        "soft_skills": [str(x) for x in (gap.get("soft_skills") or []) if x],
        "certifications": [str(x) for x in (gap.get("certifications") or []) if x],
    }


def _coerce_course_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or item.get("course_name") or item.get("name") or "").strip()
    if not title:
        return None
    platform = str(
        item.get("platform") or item.get("organization") or item.get("provider") or ""
    ).strip()
    url = str(item.get("url") or "").strip()
    out: dict[str, Any] = {"title": title, "platform": platform or "Gợi ý chung"}
    if url and not is_generic_site_url(url):
        out["url"] = url
    return out


def _coerce_courses(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        coerced = _coerce_course_item(item)
        if coerced:
            out.append(coerced)
    return out


def _coerce_roadmap(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        raw_month = entry.get("month")
        if not isinstance(raw_month, int):
            try:
                entry["month"] = int(str(raw_month).strip())
            except (ValueError, TypeError):
                entry["month"] = idx
        if not isinstance(entry.get("topics"), list):
            entry["topics"] = []
        if entry.get("milestone") is None:
            entry["milestone"] = ""
        entry["courses"] = _coerce_courses(entry.get("courses"))
        out.append(entry)
    return out


def roadmap_has_month_courses(roadmap: list[dict[str, Any]]) -> bool:
    return any(isinstance(m.get("courses"), list) and m["courses"] for m in roadmap)


def _distribute_flat_courses_to_roadmap(
    roadmap: list[dict[str, Any]],
    flat_courses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Backward compat: gán recommended_courses phẳng vào từng tháng nếu thiếu."""
    if not roadmap or not flat_courses or roadmap_has_month_courses(roadmap):
        return roadmap
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(roadmap):
        entry = dict(item)
        assigned: list[dict[str, Any]] = []
        for j in range(idx, len(flat_courses), len(roadmap)):
            assigned.append(flat_courses[j])
        entry["courses"] = _coerce_courses(assigned)
        out.append(entry)
    return out


def flatten_roadmap_courses(roadmap: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gom khóa học từ các tháng thành danh sách phẳng (dedupe theo title)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in roadmap:
        for course in _coerce_courses(item.get("courses")):
            key = course["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(course)
    return out


def _coerce_estimated_months(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_advice_payload(
    raw: Any,
    *,
    raw_response: str | None = None,
) -> dict[str, Any]:
    """Single entry point: LLM JSON, DB row, or cache → canonical advice dict."""
    src = raw if isinstance(raw, dict) else {}
    summary = (
        str(src.get("summary_vi") or src.get("raw_response") or raw_response or "")
        .strip()
    )
    roadmap = _coerce_roadmap(src.get("roadmap"))
    flat_courses = _coerce_courses(src.get("recommended_courses"))
    if roadmap and not roadmap_has_month_courses(roadmap) and flat_courses:
        roadmap = _distribute_flat_courses_to_roadmap(roadmap, flat_courses)
    month_courses = flatten_roadmap_courses(roadmap) if roadmap else []
    recommended = month_courses or flat_courses
    out: dict[str, Any] = {
        "skills_gap": normalize_skills_gap(src.get("skills_gap")),
        "roadmap": roadmap,
        "recommended_courses": recommended,
        "estimated_months": _coerce_estimated_months(src.get("estimated_months")),
        "summary_vi": summary,
    }
    stored_raw = str(src.get("raw_response") or "").strip()
    if stored_raw:
        out["raw_response"] = stored_raw
    elif summary:
        out["raw_response"] = summary
    for key in ("id", "session_id", "profile_id", "created_at"):
        if src.get(key) is not None:
            out[key] = src[key]
    return out
