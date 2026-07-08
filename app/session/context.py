from __future__ import annotations

import re

from app.intent.models import Intent, IntentRouteResult
from app.session.store import SessionState

_COURSE_FOLLOWUP = re.compile(
    r"khóa\s*học|khoa\s*hoc|course|học\s+.*\s+nào|gợi\s*ý\s*khóa|"
    r"khóa\s+\w+\s+nào|nên\s+học\s+gì",
    re.IGNORECASE,
)

_COMPETENCY_HINT = re.compile(
    r"\b(SQL|Python|Java|JavaScript|React|Docker|Kubernetes|AWS|"
    r"HTML|CSS|Node\.?js|C\+\+|C#|PHP|Go|Rust|TypeScript)\b",
    re.IGNORECASE,
)


def build_router_user_message(state: SessionState, user_text: str) -> str:
    """Ghép ngữ cảnh phiên vào prompt router (Bước 3)."""
    text = user_text.strip()
    ctx = _session_context_block(state)
    if not ctx:
        return f"Câu hỏi người dùng (lượt hiện tại):\n{text}"

    return (
        f"{ctx}\n"
        f"Câu hỏi người dùng (lượt hiện tại):\n{text}\n\n"
        "Gợi ý: nếu câu ngắn chỉ hỏi khóa học cho một kỹ năng mà career đã biết ở trên, "
        "ưu tiên course_rec và giữ career trong entities."
    )


def build_history_block(state: SessionState, *, max_turns: int = 6) -> str:
    recent = state.messages[-max_turns:]
    if not recent:
        return ""
    lines = ["## Lịch sử hội thoại gần đây"]
    for turn in recent:
        label = "User" if turn.role == "user" else "Bot"
        lines.append(f"- {label}: {turn.content[:300]}")
    return "\n".join(lines) + "\n"


def apply_route_to_state(state: SessionState, route: IntentRouteResult) -> None:
    state.last_intent = route.intent
    state.merge_route(route.model_dump())

    entities = route.entities
    if entities.career:
        state.career = entities.career
    if entities.competency:
        state.competency = entities.competency


def infer_followup_intent(state: SessionState, text: str) -> Intent | None:
    """Hỏi tiếp kiểu «khóa SQL nào» sau pathfinding/gap — ép course_rec nếu router lệch."""
    if not state.career:
        return None
    prior_ok = state.last_intent in ("pathfinding", "competency_slot_fill")
    phase_ok = state.phase in ("gap_summary", "course")
    if not prior_ok and not phase_ok:
        return None
    if not _COURSE_FOLLOWUP.search(text):
        return None
    if _COMPETENCY_HINT.search(text):
        return "course_rec"
    return "course_rec"


def extract_competency_hint(text: str) -> str | None:
    m = _COMPETENCY_HINT.search(text)
    return m.group(1) if m else None


def is_bulk_missing_courses_request(text: str) -> bool:
    """Câu gợi ý khóa tổng hợp (không chỉ định một kỹ năng cụ thể)."""
    raw = (text or "").strip()
    if not raw or not _COURSE_FOLLOWUP.search(raw):
        return False
    if extract_competency_hint(raw):
        return False
    from app.rag.aliases import resolve_competency_alias

    alias = resolve_competency_alias(raw)
    if not alias:
        return True
    return alias.casefold() not in raw.casefold()


def _session_context_block(state: SessionState) -> str:
    lines = ["## Ngữ cảnh phiên (đã lưu từ các lượt trước)"]
    has_any = False
    if state.career:
        lines.append(f"- career: {state.career}")
        has_any = True
    if state.competency:
        lines.append(f"- competency: {state.competency}")
        has_any = True
    if state.career and state.phase in ("collecting", "gap_summary", "course"):
        lines.append(f"- competency_phase: {state.phase}")
        if state.phase == "collecting":
            ctype = state.current_competency_type
            if ctype:
                lines.append(
                    f"- competency_flow: đang thu thập nhóm {ctype} "
                    f"({state.competency_type_index + 1}/7)"
                )
        if state.known_by_type:
            lines.append(f"- known_by_type: {state.known_by_type}")
        has_any = True
    if state.last_intent:
        lines.append(f"- intent lượt trước: {state.last_intent}")
        has_any = True
    if state.profile:
        lines.append(f"- profile: {state.profile.target_role_label}")
        lines.append("- profile_completed: có (ưu tiên roadmap_followup nếu hỏi lộ trình/khóa học tổng hợp)")
        if state.profile.known_skills:
            lines.append(f"- known_skills: {', '.join(state.profile.known_skills)}")
        has_any = True
    elif state.profile_completed:
        lines.append("- đã điền form hồ sơ: có")
        has_any = True
    hist = build_history_block(state, max_turns=4)
    if hist:
        return lines[0] + "\n" + "\n".join(lines[1:]) + "\n\n" + hist if has_any else hist
    if not has_any:
        return ""
    return "\n".join(lines) + "\n"
