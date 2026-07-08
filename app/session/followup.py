from __future__ import annotations

import re
import unicodedata

from app.intent.models import Intent, IntentRouteResult, RouteOutcome
from app.session.context import (
    extract_competency_hint,
    infer_followup_intent,
    is_bulk_missing_courses_request,
)
from app.rag.aliases import resolve_competency_alias
from app.session.store import SessionState


def _strip_diacritics(text: str) -> str:
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    return (
        "".join(c for c in norm if not unicodedata.combining(c))
        .replace("đ", "d")
        .replace("Đ", "D")
    )

_ROADMAP_FOLLOWUP = re.compile(
    r"lộ\s*trình|roadmap|khóa\s*học|khoa\s*hoc|học\s+(như|ra)\s*sao|"
    r"skills?\s*gap|điểm\s+còn\s+thiếu|gợi\s*ý\s*(học|khóa)|cần\s+học\s+gì|"
    r"muốn\s+học|nên\s+học|tư\s*vấn\s+tiếp|bước\s+tiếp",
    re.IGNORECASE,
)

# Câu hỏi tự do — KHÔNG ép thành competency_slot_fill kể cả khi đang mid-flow.
# Regex chạy trên text đã strip diacritics (tiếng Việt có dấu lẫn không dấu).
_FREE_QUESTION_RE = re.compile(
    r"(\?|la\s+gi|la\s+ai|lam\s+sao|lam\s+the\s+nao|"
    r"tai\s*sao|vi\s*sao|so\s*sanh|khac\s+nhau|"
    r"giai\s*thich|cho\s+(minh|toi|em)\s+(biet|hoi)|"
    r"toi\s+muon\s+(hoi|biet)|minh\s+muon\s+(hoi|biet)|"
    r"em\s+muon\s+(hoi|biet))",
    re.IGNORECASE,
)

# Lệnh thoát luồng thu thập 7 bước → ép orchestrator xử lý gap_summary.
_EXIT_FLOW_RE = re.compile(
    r"(bo\s*qua\s*(tat\s*ca|het|toan\s*bo)|skip\s*all|"
    r"xem\s*(tong\s*ket|ket\s*qua|luon|ngay)|"
    r"den\s*(luon|thang)?\s*(lo\s*trinh|ket\s*qua|tong\s*ket)|"
    r"di\s*den\s*(tong\s*ket|ket\s*qua)|"
    r"dung\s*(thu\s*thap|hoi)|khong\s*(thu\s*thap|hoi)\s*(nua|them)|"
    r"end\s*flow|stop\s*collecting)",
    re.IGNORECASE,
)


_REL_FOLLOWUP_RE = re.compile(
    r"^(thế còn|the con|con)\s+",
    re.IGNORECASE,
)

_COURSE_REC_PIVOT_RE = re.compile(
    r"khoa\s*hoc|\bkhoa\b|\bcourse\b|dang\s*ky|enroll|goi\s*y\s*khoa|cho\s+(minh|toi|em)\s+khoa",
    re.IGNORECASE,
)


def has_explicit_course_rec_pivot(text: str) -> bool:
    """User explicitly pivots to course recommendation after a prior turn."""
    raw = (text or "").strip()
    if not raw:
        return False
    probe = _strip_diacritics(raw)
    return bool(_COURSE_REC_PIVOT_RE.search(probe))


def _looks_like_relation_followup(state: SessionState, text: str) -> bool:
    if state.last_intent != "competency_relation":
        return False
    if has_explicit_course_rec_pivot(text):
        return False
    raw = (text or "").strip()
    if _REL_FOLLOWUP_RE.search(raw):
        return True
    if infer_competency_relation_followup(state, text):
        return True
    return len(raw.split()) <= 4 and bool(resolve_competency_alias(text))


def infer_competency_relation_followup(
    state: SessionState | None,
    text: str,
) -> str | None:
    """Continue competency_relation after short follow-up (e.g. 'Thế còn Angular?')."""
    if state is None or state.last_intent != "competency_relation":
        return None
    raw = (text or "").strip()
    if not raw:
        return None
    if has_explicit_course_rec_pivot(raw):
        return None
    if len(raw) > 80 and not _REL_FOLLOWUP_RE.search(raw):
        return None
    hint = extract_competency_hint(text) or resolve_competency_alias(text)
    if hint:
        return hint
    if _REL_FOLLOWUP_RE.search(raw) or len(raw.split()) <= 4:
        # Short utterance after relation turn — try alias on remainder
        from app.rag.aliases import resolve_competency_alias as _resolve

        cleaned = _REL_FOLLOWUP_RE.sub("", raw).strip(" ?.")
        return _resolve(cleaned) or (cleaned if cleaned else None)
    return None


def maybe_adjust_outcome(
    state: SessionState, user_text: str, outcome: RouteOutcome
) -> RouteOutcome:
    """Ưu tiên roadmap_followup sau form; sau pathfinding ép course_rec nếu hỏi khóa cụ thể.

    Chỉ ép competency_slot_fill khi router phân loại là slot_fill chung chung
    (tránh nuốt các intent rõ ràng như subject_career / course_rec / roadmap_followup
    khi user hỏi xen giữa luồng thu thập kỹ năng).
    """
    text_ascii = _strip_diacritics(user_text or "")

    rel_follow = infer_competency_relation_followup(state, user_text)
    if rel_follow:
        route = outcome.route
        route.intent = "competency_relation"
        route.confidence = "high"
        route.missing_slots = []
        route.entities.competency = rel_follow
        return RouteOutcome(
            route=route,
            reply=None,
            stop=False,
            parse_fallback=outcome.parse_fallback,
            career_normalized=outcome.career_normalized,
        )

    if (
        state.phase == "collecting"
        and state.career
        and _EXIT_FLOW_RE.search(text_ascii)
    ):
        return _apply_forced_intent(outcome, "competency_slot_fill", state)

    if (
        state.phase == "collecting"
        and state.career
        and (state.competency_type_index > 0 or state.known_by_type)
        and outcome.route.intent in ("slot_fill", "competency_slot_fill")
        and not _FREE_QUESTION_RE.search(text_ascii)
    ):
        return _apply_forced_intent(
            outcome,
            "competency_slot_fill",
            state,
        )

    roadmap = infer_roadmap_followup(state, user_text)
    if roadmap:
        return _apply_forced_intent(outcome, roadmap, state)

    if (
        state.career
        and state.phase in ("gap_summary", "course")
        and is_bulk_missing_courses_request(user_text)
    ):
        return _apply_forced_intent(outcome, "competency_slot_fill", state)

    if _looks_like_relation_followup(state, user_text):
        rel_hint = infer_competency_relation_followup(state, user_text)
        if rel_hint:
            route = outcome.route
            route.intent = "competency_relation"
            route.confidence = "high"
            route.missing_slots = []
            route.entities.competency = rel_hint
            return RouteOutcome(
                route=route,
                reply=None,
                stop=False,
                parse_fallback=outcome.parse_fallback,
                career_normalized=outcome.career_normalized,
            )

    forced = infer_followup_intent(state, user_text)
    if not forced:
        return outcome

    route = outcome.route
    if route.intent == "course_rec" and route.entities.competency:
        if not route.entities.career and state.career:
            route.entities.career = state.career
        return outcome

    hint = extract_competency_hint(user_text) or state.competency
    if not hint:
        return outcome

    route.intent = "course_rec"
    route.entities.competency = hint
    if state.career:
        route.entities.career = state.career
    route.missing_slots = [s for s in route.missing_slots if s != "competency"]
    route.confidence = "high"

    return _apply_forced_intent(outcome, "course_rec", state, competency=hint)


def infer_roadmap_followup(state: SessionState, text: str) -> Intent | None:
    """Sau khi điền form — câu hỏi tổng hợp lộ trình / khóa học / skills gap."""
    if not state.profile_completed:
        return None
    if not _ROADMAP_FOLLOWUP.search(text):
        return None
    hint = extract_competency_hint(text)
    if hint and re.search(
        r"khóa\s+\w+\s+nào|khóa\s*học\s+cho\s+\w+$",
        text,
        re.IGNORECASE,
    ):
        return None
    return "roadmap_followup"


def _apply_forced_intent(
    outcome: RouteOutcome,
    intent: Intent,
    state: SessionState,
    *,
    competency: str | None = None,
) -> RouteOutcome:
    route = outcome.route
    route.intent = intent
    route.confidence = "high"
    route.missing_slots = []
    if state.career:
        route.entities.career = state.career
    if competency:
        route.entities.competency = competency
    return RouteOutcome(
        route=route,
        reply=None,
        stop=False,
        parse_fallback=outcome.parse_fallback,
        career_normalized=outcome.career_normalized,
    )
