from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.rag.aliases import (
    all_keywords_for_competency,
    all_keywords_for_soft_skill,
    all_keywords_for_subject,
    keywords_block,
    resolve_alias_any,
)

_ENRICHED_PATH = Path(__file__).resolve().parents[2] / "data" / "enriched_descriptions.json"

_COMPETENCY_LABELS = [
    "ProgrammingLanguage",
    "Framework",
    "Platform",
    "Tool",
    "Knowledge",
    "Softskill",
    "Certification",
]

_USER_PHRASES_COURSE = (
    "khóa học online, MOOC, chứng chỉ, cho người mới, từ zero, "
    "self-paced, có certificate"
)
_USER_PHRASES_CAREER = (
    "lộ trình nghề, kỹ năng cần học, fresher, chuyển ngành, "
    "đi làm IT, học gì trước"
)


def _load_enriched() -> dict[str, str]:
    if not _ENRICHED_PATH.is_file():
        return {}
    with _ENRICHED_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def build_course_index_text(row: dict[str, Any], enriched: dict[str, str]) -> str:
    code = str(row.get("course_code") or "")
    name = str(row.get("course_name") or code)
    lines = [
        f"Loại: khóa học",
        f"Khóa học: {name}",
        f"Mã: {code}",
    ]
    if row.get("organization"):
        lines.append(f"Nền tảng / tổ chức: {row['organization']}")
    if row.get("level"):
        lines.append(f"Trình độ: {row['level']}")
    if row.get("subtitle"):
        lines.append(f"Phụ đề: {row['subtitle']}")
    comps = [str(c) for c in (row.get("competencies") or []) if c]
    if comps:
        lines.append("Kỹ năng liên quan: " + ", ".join(comps[:12]))
        kw_parts: list[str] = []
        for c in comps[:6]:
            kw_parts.extend(all_keywords_for_competency(c)[:4])
            resolved = resolve_alias_any(c)
            if resolved.get("soft_skill"):
                kw_parts.extend(all_keywords_for_soft_skill(resolved["soft_skill"])[:4])
            if resolved.get("subject"):
                kw_parts.extend(all_keywords_for_subject(resolved["subject"])[:4])
        if kw_parts:
            unique_kw = list(dict.fromkeys(kw_parts))[:16]
            lines.append("Từ khóa kỹ năng: " + ", ".join(unique_kw))
    lines.append(f"Cụm tìm kiếm: {_USER_PHRASES_COURSE}")
    desc = enriched.get(f"course:{code}") or row.get("description")
    if desc:
        lines.append(f"Mô tả: {str(desc)[:600]}")
    return "\n".join(lines)


def build_career_index_text(row: dict[str, Any], enriched: dict[str, str]) -> str:
    name = str(row.get("career_name") or "")
    code = str(row.get("career_code") or "")
    lines = [
        "Loại: nghề nghiệp IT",
        f"Nghề: {name}",
    ]
    if code:
        lines.append(f"Mã nghề: {code}")
    if row.get("industry"):
        lines.append(f"Ngành: {row['industry']}")
    if row.get("taxonomy"):
        lines.append(f"Phân loại: {row['taxonomy']}")
    kb = keywords_block(name, kind="career")
    if kb:
        lines.append(kb)
    lines.append(f"Cụm tìm kiếm: {_USER_PHRASES_CAREER}")
    extra = enriched.get(f"career:{name}") or enriched.get(f"career:{code}")
    if extra:
        lines.append(f"Mô tả: {str(extra)[:400]}")
    return "\n".join(lines)


def build_competency_index_text(row: dict[str, Any], enriched: dict[str, str]) -> str:
    name = str(row.get("item_name") or row.get("item_code") or "")
    code = str(row.get("item_code") or "")
    kind = str(row.get("kind") or "")
    lines = [
        "Loại: kỹ năng / competency",
        f"Kỹ năng: {name}",
        f"Mã: {code}",
    ]
    if kind:
        lines.append(f"Nhóm: {kind}")
    kb = keywords_block(name, kind="competency")
    if kb:
        lines.append(kb)
    resolved = resolve_alias_any(name)
    soft = resolved.get("soft_skill")
    if soft:
        soft_kw = all_keywords_for_soft_skill(soft)[:12]
        if soft_kw:
            lines.append("Từ khóa kỹ năng mềm: " + ", ".join(soft_kw))
    subject = resolved.get("subject")
    if subject:
        subject_kw = all_keywords_for_subject(subject)[:12]
        if subject_kw:
            lines.append("Từ khóa học phần: " + ", ".join(subject_kw))
    lines.append("Cụm tìm kiếm: khóa học, học kỹ năng, chứng chỉ, course")
    desc = enriched.get(f"competency:{name}") or enriched.get(f"competency:{code}") or row.get(
        "description"
    )
    if desc:
        lines.append(f"Mô tả: {str(desc)[:500]}")
    return "\n".join(lines)


def append_relation_lines(
    lines: list[str],
    outgoing: list[dict[str, Any]] | None,
    *,
    max_edges: int = 8,
) -> None:
    """Enrich competency index text with prerequisite / relation edges."""
    edges = outgoing or []
    if not edges:
        return
    lines.append("Quan hệ competency (Neo4j):")
    for edge in edges[:max_edges]:
        rel = edge.get("rel_type") or edge.get("relation_type") or "RELATED"
        name = edge.get("to_name") or edge.get("to_code") or "?"
        code = edge.get("to_code") or ""
        note = edge.get("note") or ""
        suffix = f" ({code})" if code else ""
        extra = f" — {note}" if note else ""
        lines.append(f"- {rel}: {name}{suffix}{extra}")
    lines.append(
        "Cụm tìm kiếm: tiên quyết, prerequisite, học trước, built on, validates, requires"
    )


def build_competency_index_text_with_relations(
    row: dict[str, Any],
    enriched: dict[str, str],
    outgoing: list[dict[str, Any]] | None = None,
) -> str:
    lines = build_competency_index_text(row, enriched).split("\n")
    append_relation_lines(lines, outgoing)
    return "\n".join(lines)
