from __future__ import annotations

from app.rag.aliases import (
    all_keywords_for_career,
    all_keywords_for_competency,
    all_keywords_for_soft_skill,
    all_keywords_for_subject,
    competencies_from_subject,
    resolve_alias_all,
)

_RELATION_EXPANSION_PHRASES = (
    "tiên quyết",
    "prerequisite",
    "học trước",
)


def expand_query_vi(message: str, *, expand_relations: bool = False) -> str:
    """
    Mở rộng câu hỏi với canonical EN + alias để embed/search vector tốt hơn.
    Giữ nguyên câu gốc ở đầu; hỗ trợ nhiều entity trong một câu.

    expand_relations: chỉ bật cho competency retrieval / relation queries (G3).
    """
    text = (message or "").strip()
    if not text:
        return text

    resolved = resolve_alias_all(text)
    extras: list[str] = []

    for career in resolved.get("careers") or []:
        extras.append(f"Career: {career}")
        extras.extend(all_keywords_for_career(career)[:6])

    for comp in resolved.get("competencies") or []:
        extras.append(f"Skill: {comp}")
        extras.extend(all_keywords_for_competency(comp)[:4])

    for soft in resolved.get("soft_skills") or []:
        extras.append(f"Soft Skill: {soft}")
        extras.extend(all_keywords_for_soft_skill(soft)[:4])

    for subject in resolved.get("subjects") or []:
        extras.append(f"Subject: {subject}")
        extras.extend(all_keywords_for_subject(subject)[:4])
        for mapped in competencies_from_subject(subject)[:4]:
            extras.append(f"Skill: {mapped}")

    if expand_relations:
        extras.extend(_RELATION_EXPANSION_PHRASES)

    if not extras:
        return text

    seen: set[str] = set()
    unique: list[str] = []
    for part in extras:
        key = part.lower()
        if key not in seen:
            seen.add(key)
            unique.append(part)

    return text + "\n" + " | ".join(unique)
