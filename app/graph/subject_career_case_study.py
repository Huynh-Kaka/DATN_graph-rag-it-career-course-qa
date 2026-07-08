"""
C-03 — Định dạng chuỗi Subject→Career và case study minh chứng luận văn.
"""

from __future__ import annotations

from typing import Any

# Case study mô tả luồng dữ liệu kỳ vọng (in log / báo cáo).
OOP_CASE_STUDY_DOC = """
C-03 Case study — Môn Lập trình hướng đối tượng (OOP):
  Môn học [Lập trình hướng đối tượng]
    → Khóa học [Python/Java cho OOP]
    → Kỹ năng [Python | Java | OOP and Design Principles]
    → Nghề nghiệp [Backend Developer | Fullstack Developer | Data Scientist | ...]

Ví dụ chuỗi cụ thể:
  Môn học [Lập trình hướng đối tượng] -> Khóa học [Python Fundamentals]
    -> Kỹ năng [Python] -> Nghề nghiệp [Data Scientist]
  Môn học [Lập trình hướng đối tượng] -> Khóa học [Java OOP]
    -> Kỹ năng [Java] -> Nghề nghiệp [Backend Developer]
""".strip()


def format_subject_career_chain(row: dict[str, Any]) -> str:
    """Một dòng lộ trình tự nhiên: môn → khóa → kỹ năng → nghề."""
    subject = row.get("subject") or "?"
    course = row.get("course") or "?"
    competency = row.get("competency") or "?"
    career = row.get("career") or "?"
    return (
        f"Học môn {subject}, có thể theo khóa {course} "
        f"để nắm {competency}, hướng tới nghề {career}"
    )


def format_subject_career_reply(
    rows: list[dict[str, Any]],
    *,
    subject_label: str,
    query_term: str | None = None,
) -> str:
    """Tổng hợp câu trả lời chatbot cho intent subject_career."""
    if not rows:
        term = query_term or subject_label
        return (
            f"Mình chưa tìm thấy liên kết môn học «{term}» với nghề nghiệp IT trong đồ thị.\n"
            "Bạn thử gọi tên môn đầy đủ hơn (ví dụ: Lập trình hướng đối tượng, Cơ sở dữ liệu, "
            "Trí tuệ nhân tạo) hoặc hỏi lộ trình một nghề cụ thể."
        )

    careers: dict[str, list[str]] = {}
    chains: list[str] = []
    for row in rows[:12]:
        chain = format_subject_career_chain(row)
        chains.append(chain)
        career = str(row.get("career") or "")
        comp = str(row.get("competency") or "")
        if career:
            careers.setdefault(career, [])
            if comp and comp not in careers[career]:
                careers[career].append(comp)

    lines = [
        f"Môn {subject_label} liên quan đến các hướng nghề IT sau:",
        "",
    ]
    for career, comps in sorted(careers.items()):
        skill_txt = ", ".join(comps[:6])
        if len(comps) > 6:
            skill_txt += f" (+{len(comps) - 6} kỹ năng khác)"
        lines.append(f"• {career} — kỹ năng nền: {skill_txt}")

    lines.extend(["", "Ví dụ lộ trình cụ thể:"])
    for chain in chains[:6]:
        lines.append(f"  - {chain}.")
    if len(chains) > 6:
        lines.append(f"  - ... và {len(chains) - 6} lộ trình khác")

    lines.append(
        "\nBạn muốn xem lộ trình chi tiết cho nghề nào, "
        "hoặc gợi ý khóa học phù hợp?"
    )
    return "\n".join(lines)


def log_case_study_sample(rows: list[dict[str, Any]], *, logger: Any) -> None:
    """Ghi log case study C-03 để minh chứng báo cáo."""
    logger.info("=== C-03 Subject→Career case study ===")
    if not rows:
        logger.info("Không có chuỗi Subject→Career từ Neo4j (rows=0).")
        return
    logger.info("%s", OOP_CASE_STUDY_DOC)
    for row in rows[:5]:
        logger.info("%s", format_subject_career_chain(row))
