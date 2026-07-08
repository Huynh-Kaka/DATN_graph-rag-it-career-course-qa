"""
Cấu trúc phản hồi cho frontend (cards / timeline / chips) — không dùng markdown thô.
"""

from __future__ import annotations

from typing import Any, Literal

from app.advice.schema import normalize_advice_payload, roadmap_has_month_courses
from pydantic import BaseModel, Field

SectionType = Literal[
    "summary",
    "skills_gap",
    "timeline",
    "courses_by_skill",
    "courses",
    "meta",
    "competency_collection",
    "competency_gap_summary",
]


class StructuredSection(BaseModel):
    type: SectionType
    title: str | None = None
    text: str | None = None
    chips_known: list[str] = Field(default_factory=list)
    chips_missing: list[str] = Field(default_factory=list)
    chips_weak: list[str] = Field(default_factory=list)
    chips_soft_skills: list[str] = Field(default_factory=list)
    chips_certifications: list[str] = Field(default_factory=list)
    # C-01: chip kèm badge ưu tiên (frontend render badge thay vì chỉ tên).
    chips_missing_meta: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    courses_by_skill: list[dict[str, Any]] = Field(default_factory=list)
    courses: list[dict[str, Any]] = Field(default_factory=list)
    estimated_months: int | None = None
    career: str | None = None
    # competency_collection: chips_suggested / progress / step / total / actions.
    step: int | None = None
    total: int | None = None
    type_code: str | None = None
    type_label: str | None = None
    chips_suggested: list[str] = Field(default_factory=list)
    progress: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    hint: str | None = None


class StructuredReply(BaseModel):
    title: str = "Tư vấn hướng nghiệp IT"
    sections: list[StructuredSection] = Field(default_factory=list)

    def model_dump_public(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _timeline_month_label(month: Any, *, fallback_index: int) -> str:
    if isinstance(month, int):
        return f"Tháng {month}"
    try:
        return f"Tháng {int(str(month).strip())}"
    except (ValueError, TypeError):
        return f"Giai đoạn {fallback_index}"


def _format_timeline_plain_line(item: dict[str, Any], *, index: int) -> str:
    month = item.get("month")
    topics = [str(t) for t in (item.get("topics") or []) if t]
    milestone = str(item.get("milestone") or "").strip()
    label = _timeline_month_label(month, fallback_index=index)
    if topics and milestone:
        head = f"  {label}: {', '.join(topics)} — {milestone}"
    elif topics:
        head = f"  {label}: {', '.join(topics)}"
    elif milestone:
        head = f"  {label}: {milestone}"
    else:
        head = f"  {label}"
    course_lines = [
        _format_course_plain_line(c)
        for c in (item.get("courses") or [])
        if isinstance(c, dict)
    ]
    if course_lines:
        return head + "\n" + "\n".join(course_lines)
    return head


def _format_course_plain_line(course: dict[str, Any]) -> str:
    name = (
        course.get("title")
        or course.get("course_name")
        or course.get("name")
        or "Khóa học"
    )
    platform = course.get("organization") or course.get("platform") or ""
    url = str(course.get("url") or "").strip()
    parts = [f"  • {name}"]
    if platform:
        parts.append(f"({platform})")
    line = " ".join(parts)
    if url:
        line += f"\n    {url}"
    return line


def plain_text_from_structured(structured: StructuredReply) -> str:
    """Fallback text khi client không render structured."""
    lines: list[str] = []
    for sec in structured.sections:
        if sec.type == "summary" and sec.text:
            lines.append(sec.text.strip())
        elif sec.type == "skills_gap":
            if sec.chips_known:
                lines.append("Đã có: " + ", ".join(sec.chips_known))
            if sec.chips_missing:
                lines.append("Cần học: " + ", ".join(sec.chips_missing))
            if sec.chips_weak:
                lines.append("Nên củng cố: " + ", ".join(sec.chips_weak))
            if sec.chips_soft_skills:
                lines.append("Kỹ năng mềm: " + ", ".join(sec.chips_soft_skills))
            if sec.chips_certifications:
                lines.append("Chứng chỉ tham khảo: " + ", ".join(sec.chips_certifications))
        elif sec.type == "timeline" and sec.timeline:
            lines.append("Lộ trình gợi ý:")
            for idx, item in enumerate(sec.timeline, start=1):
                if isinstance(item, dict):
                    lines.append(_format_timeline_plain_line(item, index=idx))
        elif sec.type == "courses" and sec.courses:
            lines.append(f"\n{sec.title or 'Khóa học gợi ý'}:")
            for course in sec.courses:
                if isinstance(course, dict):
                    lines.append(_format_course_plain_line(course))
        elif sec.type == "courses_by_skill" and sec.courses_by_skill:
            for block in sec.courses_by_skill:
                skill = block.get("skill") or "Kỹ năng"
                lines.append(f"\nKhóa học cho {skill}:")
                for c in block.get("courses") or []:
                    title = c.get("title") or c.get("course_name") or "Khóa học"
                    org = c.get("organization") or c.get("platform") or ""
                    lines.append(f"  - {title}" + (f" ({org})" if org else ""))
        elif sec.type == "meta" and sec.estimated_months:
            lines.append(f"Dự kiến sẵn sàng đi làm: ~{sec.estimated_months} tháng.")
        elif sec.type == "competency_collection":
            if sec.title:
                lines.append(sec.title)
            if sec.chips_known:
                lines.append("Đã ghi: " + ", ".join(sec.chips_known))
            if sec.chips_suggested:
                lines.append("Gợi ý: " + ", ".join(sec.chips_suggested))
            if sec.text:
                lines.append(sec.text)
        elif sec.type == "competency_gap_summary":
            if sec.chips_known:
                lines.append("Đã có: " + ", ".join(sec.chips_known))
            if sec.chips_missing:
                lines.append("Cần học: " + ", ".join(sec.chips_missing))
    return "\n\n".join(lines) if lines else "Không có nội dung tư vấn."


def priority_badge(priority: int | None) -> str | None:
    """Nhãn badge cho NEED_*.priority_group (nhóm nhỏ = cốt lõi)."""
    if priority is None:
        return None
    if priority == 1:
        return "Cốt lõi"
    return f"Nhóm {priority}"


def coverage_badge(level: int | None) -> str | None:
    """Nhãn badge cho TEACH_*.coverage_level."""
    if level is None:
        return None
    return f"Bao phủ {level}"


def course_item_to_chip(c: dict[str, Any]) -> dict[str, Any]:
    cov = c.get("coverage_level")
    if cov is not None:
        try:
            cov = int(cov)
        except (TypeError, ValueError):
            cov = None
    return {
        "title": c.get("course_name") or c.get("title") or "",
        "organization": c.get("organization") or c.get("platform") or "",
        "level": c.get("level") or "",
        "subtitle": c.get("subtitle") or "",
        "url": c.get("url") or "",
        "duration_hours": c.get("duration_hours"),
        "coverage_level": cov,
        "coverage_badge": coverage_badge(cov),
    }


def skill_chip_meta(name: str, *, priority: int | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "priority": priority,
        "priority_badge": priority_badge(priority),
    }


def structured_from_pathfinding(
    pf: Any,
    *,
    summary: str | None = None,
    career: str | None = None,
    scope_label: str | None = None,
) -> StructuredReply:
    known_items = getattr(pf, "skills_known", []) or []
    missing_items = getattr(pf, "skills_missing", []) or []
    known = [c.name for c in known_items]
    missing_meta = [
        skill_chip_meta(c.name, priority=c.priority) for c in missing_items
    ]
    missing = [m["name"] for m in missing_meta]
    title_career = getattr(pf, "career_name", None) or career or "nghề mục tiêu"
    if scope_label:
        title = f"{scope_label} cho {title_career}"
        gap_title = f"Phân tích khoảng cách — {scope_label}"
    else:
        title = f"Kỹ năng cho {title_career}"
        gap_title = "Phân tích khoảng cách kỹ năng"
    sections: list[StructuredSection] = []
    if summary:
        sections.append(StructuredSection(type="summary", text=summary))
    sections.append(
        StructuredSection(
            type="skills_gap",
            title=gap_title,
            chips_known=known,
            chips_missing=missing,
            chips_missing_meta=missing_meta,
            career=title_career,
        )
    )
    return StructuredReply(title=title, sections=sections)


def structured_from_advice(
    advice: dict[str, Any],
    *,
    career: str | None = None,
    known_skills: list[str] | None = None,
) -> StructuredReply:
    norm = normalize_advice_payload(advice)
    gap = norm["skills_gap"]
    known_labels = _labels_from_form_codes(known_skills or [])
    roadmap = list(norm.get("roadmap") or [])
    timeline_items = [
        {
            **item,
            "courses": [
                course_item_to_chip(c) if isinstance(c, dict) else course_item_to_chip({})
                for c in (item.get("courses") or [])
            ],
        }
        for item in roadmap
        if isinstance(item, dict)
    ]
    sections: list[StructuredSection] = [
        StructuredSection(
            type="summary",
            text=(norm.get("raw_response") or norm.get("summary_vi") or "").strip(),
        ),
        StructuredSection(
            type="skills_gap",
            title="Khoảng cách kỹ năng",
            chips_known=_display_normalize_skill_labels(known_labels),
            chips_missing=_display_normalize_skill_labels(
                list(gap.get("missing") or [])
            ),
            chips_weak=_display_normalize_skill_labels(
                list(gap.get("weak") or [])
            ),
            chips_soft_skills=_display_normalize_skill_labels(
                list(gap.get("soft_skills") or [])
            ),
            chips_certifications=_display_normalize_skill_labels(
                list(gap.get("certifications") or [])
            ),
            career=career,
        ),
        StructuredSection(
            type="timeline",
            title="Lộ trình theo tháng",
            timeline=timeline_items,
            estimated_months=norm.get("estimated_months"),
        ),
    ]
    if not roadmap_has_month_courses(roadmap):
        flat = norm.get("recommended_courses") or []
        if flat:
            sections.append(
                StructuredSection(
                    type="courses",
                    title="Khóa học gợi ý",
                    courses=[
                        course_item_to_chip(c) if isinstance(c, dict) else course_item_to_chip({})
                        for c in flat
                    ],
                )
            )
    sections.append(
        StructuredSection(
            type="meta",
            estimated_months=norm.get("estimated_months"),
            career=career,
        )
    )
    return StructuredReply(
        title=f"Tư vấn — {career or 'mục tiêu của bạn'}",
        sections=sections,
    )


def structured_from_competency_card(
    card: dict[str, Any], *, summary: str | None = None
) -> StructuredReply:
    """Card chip + progress cho luồng thu thập kỹ năng (Bước X/7)."""
    type_label = card.get("type_label") or "Kỹ năng"
    career = card.get("career") or "nghề mục tiêu"
    step = card.get("step")
    total = card.get("total")
    title = f"Bước {step}/{total} — {type_label}" if step and total else type_label
    sections: list[StructuredSection] = []
    if summary:
        sections.append(StructuredSection(type="summary", text=summary))
    sections.append(
        StructuredSection(
            type="competency_collection",
            title=title,
            text=card.get("hint"),
            career=career,
            step=step,
            total=total,
            type_code=card.get("type_code"),
            type_label=type_label,
            chips_known=list(card.get("already_known") or []),
            chips_suggested=list(card.get("suggested_chips") or []),
            progress=list(card.get("progress") or []),
            actions=list(card.get("actions") or []),
        )
    )
    return StructuredReply(title=f"Thu thập kỹ năng — {career}", sections=sections)


def structured_from_gap_summary(
    card: dict[str, Any], *, summary: str | None = None
) -> StructuredReply:
    """Card tổng kết khoảng cách kỹ năng + CTA gợi ý khóa học."""
    career = card.get("career") or "nghề mục tiêu"
    sections: list[StructuredSection] = []
    if summary:
        sections.append(StructuredSection(type="summary", text=summary))
    sections.append(
        StructuredSection(
            type="competency_gap_summary",
            title=f"Khoảng cách kỹ năng — {career}",
            career=career,
            chips_known=list(card.get("known") or []),
            chips_missing=list(card.get("missing") or []),
            actions=list(card.get("actions") or []),
        )
    )
    return StructuredReply(title=f"Khoảng cách kỹ năng — {career}", sections=sections)


def structured_from_gap_courses(
    card: dict[str, Any],
    courses_by_skill: list[dict[str, Any]],
    *,
    summary: str | None = None,
) -> StructuredReply:
    """Gap summary + khóa học theo từng kỹ năng còn thiếu."""
    career = card.get("career") or "nghề mục tiêu"
    sections: list[StructuredSection] = []
    if summary:
        sections.append(StructuredSection(type="summary", text=summary))
    sections.append(
        StructuredSection(
            type="competency_gap_summary",
            title=f"Khoảng cách kỹ năng — {career}",
            career=career,
            chips_known=list(card.get("known") or []),
            chips_missing=list(card.get("missing") or []),
            actions=list(card.get("actions") or []),
        )
    )
    if courses_by_skill:
        sections.append(
            StructuredSection(
                type="courses_by_skill",
                title="Khóa học theo kỹ năng cần học",
                courses_by_skill=courses_by_skill,
            )
        )
    return StructuredReply(title=f"Khóa học gợi ý — {career}", sections=sections)


def structured_from_course_rec(cr: Any, *, summary: str | None = None) -> StructuredReply:
    skill = getattr(cr, "competency_name", None) or "Kỹ năng"
    courses = [
        course_item_to_chip(c.model_dump())
        for c in getattr(cr, "courses", [])[:15]
    ]
    sections: list[StructuredSection] = []
    if summary:
        sections.append(StructuredSection(type="summary", text=summary))
    sections.append(
        StructuredSection(
            type="courses",
            title=f"Khóa học — {skill}",
            courses=courses,
            career=None,
        )
    )
    return StructuredReply(title=f"Khóa học {skill}", sections=sections)


def _labels_from_form_codes(codes: list[str]) -> list[str]:
    from app.graph.skills_gap import FORM_SKILL_ALIASES

    labels: list[str] = []
    for code in codes:
        key = (code or "").strip().lower()
        if not key or key == "none":
            continue
        aliases = FORM_SKILL_ALIASES.get(key)
        if aliases:
            canonical = aliases[0]
            if canonical == "javascript":
                labels.append("JavaScript")
            elif canonical == "sql":
                labels.append("SQL")
            else:
                labels.append(canonical.title())
        else:
            labels.append(key.title())
    return labels


def _display_normalize_skill_labels(labels: list[str]) -> list[str]:
    """
    Chuẩn hoá cách hiển thị để tránh trường hợp:
    - code từ form: "sql" -> "Sql" (title-case)
    - missing từ graph/LLM: giữ nguyên "sql"
    """
    from app.graph.skills_gap import FORM_SKILL_ALIASES

    rev: dict[str, str] = {}
    for _, aliases in FORM_SKILL_ALIASES.items():
        if not aliases:
            continue
        canonical = aliases[0]
        # map alias token -> canonical display label
        if canonical == "javascript":
            display = "JavaScript"
        elif canonical == "sql":
            display = "SQL"
        else:
            display = canonical.title()
        for a in aliases:
            rev[(a or "").strip().lower()] = display

    out: list[str] = []
    for l in labels or []:
        token = (l or "").strip()
        if not token:
            continue
        key = token.lower()
        out.append(rev.get(key) or token.title())
    return out
