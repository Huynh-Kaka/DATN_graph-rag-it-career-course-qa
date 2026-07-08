from __future__ import annotations

from app.rag.aliases import all_keywords_for_career, all_keywords_for_competency


def pathfinding_questions(career_canonical: str, *, max_questions: int = 5) -> list[str]:
    """Paraphrase câu hỏi pathfinding từ alias (đồng bộ Qdrant + SFT)."""
    keys = all_keywords_for_career(career_canonical)
    templates = [
        "Làm {k} cần học những gì?",
        "Lộ trình trở thành {k}?",
        "Kỹ năng cần có cho {k}?",
        "Muốn theo nghề {k} thì học gì trước?",
        "{k} cần biết gì?",
    ]
    out: list[str] = []
    for i, tpl in enumerate(templates):
        if i >= max_questions:
            break
        k = keys[i % len(keys)] if keys else career_canonical
        out.append(tpl.format(k=k))
    return out


def course_rec_questions(competency_canonical: str, *, max_questions: int = 4) -> list[str]:
    keys = all_keywords_for_competency(competency_canonical)
    templates = [
        "Khóa học {k} nào phù hợp?",
        "Gợi ý khóa {k} cho người mới?",
        "Muốn học {k} thì chọn khóa nào?",
        "Có khóa {k} nào trên thị trường không?",
    ]
    out: list[str] = []
    for i, tpl in enumerate(templates):
        if i >= max_questions:
            break
        k = keys[i % len(keys)] if keys else competency_canonical
        out.append(tpl.format(k=k))
    return out


def user_prompt_keywords_block(
    *,
    career: str | None = None,
    competency: str | None = None,
) -> str:
    lines: list[str] = []
    if career:
        keys = all_keywords_for_career(career)
        if keys:
            lines.append("## Từ khóa người dùng có thể dùng (nghề)")
            lines.append(", ".join(keys[:15]))
    if competency:
        keys = all_keywords_for_competency(competency)
        if keys:
            lines.append("## Từ khóa người dùng có thể dùng (kỹ năng)")
            lines.append(", ".join(keys[:15]))
    return "\n".join(lines) + ("\n" if lines else "")
