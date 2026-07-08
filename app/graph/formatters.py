from __future__ import annotations

from collections import defaultdict

from app.graph.models import (
    CompetencyRelationEdge,
    CompetencyRelationResult,
    CourseRecResult,
    PathfindingResult,
)
from app.session.store import SessionState

_REL_TYPE_LABEL_VI: dict[str, str] = {
    "BUILT_ON": "được xây dựng trên",
    "VALIDATES": "chứng nhận",
    "SUPPORTS": "hỗ trợ",
    "REQUIRES": "yêu cầu",
    "REQUIRES_KNOWLEDGE": "cần kiến thức về",
    "PREFERS_LANG": "ưu tiên ngôn ngữ",
}


def _rel_type_label_vi(rel_type: str) -> str:
    return _REL_TYPE_LABEL_VI.get(rel_type, rel_type.replace("_", " ").lower())


def _format_outgoing_edge(anchor_name: str, edge: CompetencyRelationEdge) -> str:
    if edge.note:
        note = edge.note.strip()
        if not note.endswith((".", "!", "?")):
            note += "."
        return note
    target = edge.to_name
    rt = edge.rel_type
    if rt == "BUILT_ON":
        return (
            f"{anchor_name} được xây dựng trên {target} — "
            f"bạn nên học {target} trước."
        )
    if rt == "VALIDATES":
        return f"{anchor_name} chứng nhận năng lực {target}."
    if rt == "SUPPORTS":
        return f"{anchor_name} hỗ trợ cho {target}."
    if rt == "REQUIRES":
        return f"Để phát triển {anchor_name}, bạn cần {target}."
    if rt == "REQUIRES_KNOWLEDGE":
        return f"{anchor_name} cần kiến thức về {target}."
    label = _rel_type_label_vi(rt)
    return f"{anchor_name} {label} {target}."


def _format_incoming_edge(anchor_name: str, edge: CompetencyRelationEdge) -> str:
    if edge.note:
        note = edge.note.strip()
        if not note.endswith((".", "!", "?")):
            note += "."
        return note
    source = edge.from_name
    rt = edge.rel_type
    if rt == "VALIDATES":
        return f"Chứng chỉ {source} chứng nhận năng lực {anchor_name}."
    if rt == "BUILT_ON":
        return f"{source} được xây dựng trên {anchor_name}."
    if rt == "SUPPORTS":
        return f"{source} hỗ trợ cho {anchor_name}."
    if rt == "REQUIRES":
        return f"{source} yêu cầu {anchor_name}."
    if rt == "REQUIRES_KNOWLEDGE":
        return f"{source} cần kiến thức về {anchor_name}."
    label = _rel_type_label_vi(rt)
    return f"{source} {label} {anchor_name}."


def format_pathfinding(result: PathfindingResult, state: SessionState | None = None) -> str:
    if not result.found:
        return result.error or "Không tra cứu được lộ trình nghề."

    lines: list[str] = [
        f"## Kỹ năng cần cho {result.career_name}",
    ]
    if result.industry:
        lines.append(f"Ngành: {result.industry}")
    if result.error and result.competencies:
        lines.append(f"_{result.error}_")
    elif result.error:
        return result.error

    if result.skills_known or result.skills_missing:
        if result.skills_known:
            lines.append("\n**Đã có:** " + ", ".join(c.name for c in result.skills_known))
        if result.skills_missing:
            lines.append("**Cần học:** " + ", ".join(c.name for c in result.skills_missing))
        lines.append("")

    comps_for_groups = result.skills_missing or result.competencies
    by_kind: dict[str, list[str]] = defaultdict(list)
    for c in comps_for_groups:
        label = c.name
        if c.priority is not None:
            label += f" (ưu tiên {c.priority})"
        by_kind[c.kind].append(label)

    kind_order = [
        "ProgrammingLanguage",
        "Framework",
        "Platform",
        "Tool",
        "Knowledge",
        "Softskill",
        "Certification",
    ]
    ordered_kinds = sorted(
        by_kind.keys(),
        key=lambda k: (kind_order.index(k) if k in kind_order else 99, k),
    )

    for kind in ordered_kinds:
        names = by_kind[kind]
        lines.append(f"\n### {kind}")
        for n in names:
            lines.append(f"- {n}")

    advisory = [
        a
        for c in comps_for_groups
        for a in (c.advisory_prerequisites or [])
        if a
    ]
    if advisory:
        lines.append("\n### Nên học trước (gợi ý từ graph)")
        for a in advisory[:8]:
            lines.append(f"- {a}")

    lines.append(
        "\nBạn muốn gợi ý khóa học cho kỹ năng cụ thể nào? "
        "Hãy hỏi ví dụ: «Khóa Python nào phù hợp?»"
    )
    return "\n".join(lines)


def format_course_rec(result: CourseRecResult) -> str:
    if not result.found:
        return result.error or "Không tra cứu được khóa học."

    if result.error and not result.courses:
        return result.error

    lines = [
        f"## Khóa học cho {result.competency_name}",
    ]
    if result.competency_kind:
        lines.append(f"Loại kỹ năng: {result.competency_kind}")

    if result.via_prerequisites:
        lines.append(
            "\nChưa có khóa trực tiếp — gợi ý học nền tảng trước:"
        )
        for block in result.via_prerequisites:
            lines.append(f"\nNền tảng: {block.get('name')}")
            for i, raw in enumerate(block.get("courses") or [], start=1):
                if isinstance(raw, dict):
                    lines.append(f"  {i}. {raw.get('course_name', raw.get('course_code'))}")

    if not result.courses:
        return result.error or "Chưa có khóa học trong graph cho kỹ năng này."

    for i, c in enumerate(result.courses[:15], start=1):
        parts = [f"**{i}. {c.course_name}**"]
        meta: list[str] = []
        if c.organization:
            meta.append(f"Tổ chức: {c.organization}")
        if c.level:
            meta.append(f"Cấp độ: {c.level}")
        if c.subtitle:
            meta.append(f"Phụ đề: {c.subtitle}")
        if c.duration_hours:
            meta.append(f"Thời lượng: {c.duration_hours} giờ")
        if c.coverage_level is not None:
            meta.append(f"Bao phủ: {c.coverage_level}")
        if meta:
            parts.append(" · ".join(meta))
        if c.url:
            parts.append(f"Link: {c.url}")
        lines.append("\n".join(parts))

    if len(result.courses) > 15:
        lines.append(f"\n_… và {len(result.courses) - 15} khóa khác._")

    return "\n\n".join(lines)


EMPTY_RELATION_MARKER = "Graph chưa có quan hệ"

EMPTY_RELATION_REPLY = (
    f"{EMPTY_RELATION_MARKER} tiên quyết/chứng nhận cho «{{name}}». "
    "Bạn có thể hỏi lộ trình nghề hoặc khóa học trực tiếp."
)


def format_competency_relation(result: CompetencyRelationResult) -> str:
    if result.error == "ambiguous_competency" and result.resolve_candidates:
        opts = ", ".join(
            f"{c.get('item_name')} ({c.get('item_code')})"
            for c in result.resolve_candidates[:4]
            if c.get("item_name")
        )
        return f"Bạn muốn hỏi về kỹ năng nào trong các lựa chọn: {opts}?"

    name = result.anchor_name or "kỹ năng này"

    if result.coverage == "none" or not (result.outgoing or result.incoming):
        return EMPTY_RELATION_REPLY.format(name=name)

    lines = [f"Với {name}, bạn cần lưu ý:"]

    for edge in result.outgoing:
        lines.append(f"• {_format_outgoing_edge(name, edge)}")

    for edge in result.incoming:
        lines.append(f"• {_format_incoming_edge(name, edge)}")

    lines.append(
        "\nBạn muốn gợi ý khóa học cho kỹ năng nào? "
        "Hãy hỏi ví dụ: «Khóa Python nào phù hợp?»"
    )
    return "\n".join(lines)
