"""Thứ tự ưu tiên khóa học từ Neo4j — URL khóa học cụ thể trước coverage."""

from __future__ import annotations

from typing import Any

from app.advice.schema import is_generic_site_url


def course_raw_sort_key(raw: dict[str, Any]) -> tuple:
    """Ưu tiên: có course.url hợp lệ → coverage cao → seed."""
    url = str(raw.get("url") or "").strip()
    has_url = 0 if url and not is_generic_site_url(url) else 1
    try:
        cov = float(raw.get("coverage_level") or 0)
    except (TypeError, ValueError):
        cov = 0.0
    seed = 0 if raw.get("is_seed") else 1
    name = str(raw.get("course_name") or raw.get("title") or "")
    return (has_url, -cov, seed, name)


def course_item_sort_key(
    *,
    url: str | None,
    coverage_level: int | None,
    is_seed: bool,
    course_name: str,
) -> tuple:
    has_url = 0 if (url or "").strip() and not is_generic_site_url(url) else 1
    cov = float(coverage_level or 0)
    return (has_url, -cov, 0 if is_seed else 1, course_name)
