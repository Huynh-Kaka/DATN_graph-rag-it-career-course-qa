"""
Sequential competency-type flow (7 blocks: LANG → … → CERT).

Ten-step orchestration:
 1. Ensure career is set on session
 2. Skip empty NEED_* types for this career (auto-advance index)
 3. Prompt user for skills in the current competency block
 4. Parse user message → competency/soft/subject aliases
 5. Merge parsed skills into known_by_type[current_type]
 6. Advance index or finish collecting phase
 7. Build typed gap via apply_skills_gap_typed (gap_summary phase)
 8. Format gap summary text for the user
 9. Optional course phase — recommend courses per missing skill
10. Mark flow complete / allow router to resume normal intents
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.graph.models import PathfindingResult
from app.graph.repository import GraphRepository
from app.graph.course_suggestions import build_courses_by_skill_blocks
from app.graph.skills_gap import apply_skills_gap_typed, merge_typed_gap_results
from app.rag.aliases import (
    competencies_from_subject,
    resolve_all_competency_aliases,
    resolve_all_soft_skill_aliases,
    resolve_all_subject_aliases,
)
from app.session.competency_types import (
    COMPETENCY_TYPE_ORDER,
    need_rel_for_type,
    type_label,
)
from app.session.store import SessionState

_SKIP_RE = re.compile(
    r"^(không|ko|k\b|none|chưa|bỏ qua|skip|bỏ|không có|chưa biết)\b",
    re.IGNORECASE,
)

# Lệnh thoát toàn bộ luồng thu thập → nhảy thẳng tới gap_summary.
# Regex chạy trên text đã strip diacritics (xem `_strip_diacritics`).
_EXIT_FLOW_RE = re.compile(
    r"(bo\s*qua\s*(tat\s*ca|het|toan\s*bo)|skip\s*all|"
    r"xem\s*(tong\s*ket|ket\s*qua|luon|ngay)|"
    r"den\s*(luon|thang)?\s*(lo\s*trinh|ket\s*qua|tong\s*ket)|"
    r"di\s*den\s*(tong\s*ket|ket\s*qua)|"
    r"dung\s*(thu\s*thap|hoi)|khong\s*(thu\s*thap|hoi)\s*(nua|them)|"
    r"end\s*flow|stop\s*collecting)",
    re.IGNORECASE,
)

# Câu hỏi tự do — match trên text đã strip diacritics.
_QUESTION_RE = re.compile(
    r"(\?|la\s+gi|la\s+ai|lam\s+sao|lam\s+the\s+nao|"
    r"tai\s*sao|vi\s*sao|so\s*sanh|khac\s+nhau|"
    r"giai\s*thich|cho\s+(minh|toi|em)\s+(biet|hoi)|"
    r"toi\s+muon\s+(hoi|biet)|minh\s+muon\s+(hoi|biet)|"
    r"em\s+muon\s+(hoi|biet))",
    re.IGNORECASE,
)


def _strip_diacritics(text: str) -> str:
    """Chuẩn hoá để regex match cả tiếng Việt có dấu lẫn không dấu."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c)).replace("đ", "d").replace("Đ", "D")


@dataclass
class OrchestratorTurn:
    handled: bool
    reply: str | None = None
    stop: bool = False
    structured: dict[str, Any] | None = None
    graph: dict[str, Any] | None = None


class CompetencyTypeOrchestrator:
    def __init__(self, graph: GraphRepository | None = None) -> None:
        self._graph = graph or GraphRepository()

    def should_handle(self, state: SessionState) -> bool:
        if not state.career:
            return False
        if state.phase == "course":
            return False
        if state.phase == "gap_summary":
            return False
        if state.competency_type_index >= len(COMPETENCY_TYPE_ORDER):
            return state.phase == "collecting"
        return state.phase == "collecting"

    def handle_turn(self, state: SessionState, user_text: str) -> OrchestratorTurn:
        if not state.career:
            return OrchestratorTurn(handled=False)

        text = (user_text or "").strip()
        text_ascii = _strip_diacritics(text)

        if text and _EXIT_FLOW_RE.search(text_ascii):
            state.phase = "gap_summary"
            return self._handle_gap_summary(state, user_text)

        if state.phase == "gap_summary":
            return self._handle_gap_summary(state, user_text)

        if state.phase == "course":
            if re.search(r"khóa|course|học\s+gì", user_text or "", re.IGNORECASE):
                return self._handle_gap_summary(state, user_text)
            return OrchestratorTurn(handled=False)

        if state.competency_type_index >= len(COMPETENCY_TYPE_ORDER):
            state.phase = "gap_summary"
            return self._handle_gap_summary(state, user_text)

        if state.phase == "idle":
            state.phase = "collecting"

        self._skip_empty_types(state)
        if state.competency_type_index >= len(COMPETENCY_TYPE_ORDER):
            state.phase = "gap_summary"
            return self._handle_gap_summary(state, user_text)

        type_code = state.current_competency_type
        if not type_code:
            return OrchestratorTurn(handled=False)

        if text:
            if self._is_skip_response(text):
                state.competency_type_index += 1
            elif _QUESTION_RE.search(text_ascii):
                # Không nuốt câu hỏi tự do của user.
                return OrchestratorTurn(handled=False)
            else:
                skills = self._extract_skills_from_message(text)
                if not skills:
                    return OrchestratorTurn(
                        handled=True,
                        reply=self._format_no_skill_recognized(state, type_code),
                        structured=self._build_card(
                            state,
                            type_code,
                            hint=(
                                f"Mình chưa nhận diện được kỹ năng nào trong '{text[:60]}'. "
                                "Bạn bấm chip dưới hoặc «Bỏ qua nhóm này»."
                            ),
                        ),
                        stop=True,
                    )
                state.record_known_for_type(type_code, skills)
                state.competency_type_index += 1
            self._skip_empty_types(state)
            if state.competency_type_index >= len(COMPETENCY_TYPE_ORDER):
                state.phase = "gap_summary"
                return self._handle_gap_summary(state, user_text)
            next_type = state.current_competency_type
            if next_type:
                return OrchestratorTurn(
                    handled=True,
                    reply=self._prompt_for_type(state, next_type),
                    structured=self._build_card(state, next_type),
                    stop=True,
                )

        return OrchestratorTurn(
            handled=True,
            reply=self._prompt_for_type(state, type_code),
            structured=self._build_card(state, type_code),
            stop=True,
        )

    def start_collection(self, state: SessionState) -> str:
        """Reset flow and return first prompt (after career is known)."""
        reply, _ = self.start_collection_with_card(state)
        return reply

    def start_collection_with_card(
        self, state: SessionState
    ) -> tuple[str, dict[str, Any] | None]:
        state.reset_competency_flow()
        self._skip_empty_types(state)
        type_code = state.current_competency_type
        if not type_code:
            state.phase = "gap_summary"
            summary, card = self._build_gap_summary_with_card(state)
            return summary, card
        return self._prompt_for_type(state, type_code), self._build_card(state, type_code)

    def _skip_empty_types(self, state: SessionState) -> None:
        career = state.career or ""
        while state.competency_type_index < len(COMPETENCY_TYPE_ORDER):
            type_code = COMPETENCY_TYPE_ORDER[state.competency_type_index]
            rel = need_rel_for_type(type_code)
            if not rel:
                state.competency_type_index += 1
                continue
            pf = self._graph.pathfinding_by_type(career, rel)
            if pf.found and pf.competencies:
                break
            state.competency_type_index += 1

    def _prompt_for_type(self, state: SessionState, type_code: str) -> str:
        career = state.career or "nghề mục tiêu"
        rel = need_rel_for_type(type_code) or ""
        pf = self._graph.pathfinding_by_type(career, rel) if rel else None
        required = [c.name for c in (pf.competencies if pf else []) if c.name]
        already = list(state.known_by_type.get(type_code) or [])
        label = type_label(type_code)
        step = state.competency_type_index + 1
        total = len(COMPETENCY_TYPE_ORDER)
        lines = [
            f"**Bước {step}/{total} — {label}** (cho {career})",
        ]
        if already:
            lines.append(f"Đã ghi từ form: {', '.join(already[:6])}.")
        if required:
            preview = ", ".join(required[:8])
            more = f" (+{len(required) - 8} nữa)" if len(required) > 8 else ""
            lines.append(f"Graph gợi ý cần: {preview}{more}.")
        lines.append(
            "Bạn chọn thêm kỹ năng đã biết, gõ «không» để bỏ qua nhóm, "
            "hoặc gõ «xem tổng kết» để đi tới khoảng cách kỹ năng."
        )
        return "\n".join(lines)

    def _format_no_skill_recognized(self, state: SessionState, type_code: str) -> str:
        label = type_label(type_code)
        career = state.career or "nghề mục tiêu"
        return (
            f"Mình chưa nhận diện được kỹ năng nào thuộc nhóm *{label}* cho {career}. "
            "Bạn có thể bấm chip dưới đây, liệt kê tên kỹ năng cách nhau bằng dấu phẩy, "
            "gõ «không» để bỏ qua nhóm, hoặc «xem tổng kết» để xem khoảng cách kỹ năng ngay."
        )

    def _build_card(
        self,
        state: SessionState,
        type_code: str,
        *,
        hint: str | None = None,
    ) -> dict[str, Any]:
        """Structured payload cho frontend render chip + progress + buttons."""
        career = state.career or "nghề mục tiêu"
        rel = need_rel_for_type(type_code) or ""
        pf = self._graph.pathfinding_by_type(career, rel) if rel else None
        suggested = [c.name for c in (pf.competencies if pf else []) if c.name]
        already = list(state.known_by_type.get(type_code) or [])
        already_lower = {s.lower() for s in already}
        # Loại chip đã có khỏi danh sách gợi ý (đã chọn = không cần chọn lại).
        chips = [s for s in suggested if s.lower() not in already_lower]
        step = state.competency_type_index + 1
        total = len(COMPETENCY_TYPE_ORDER)
        return {
            "type": "competency_collection",
            "step": step,
            "total": total,
            "type_code": type_code,
            "type_label": type_label(type_code),
            "career": career,
            "suggested_chips": chips[:12],
            "already_known": already,
            "hint": hint,
            "progress": [
                {
                    "type_code": code,
                    "type_label": type_label(code),
                    "state": (
                        "done" if i < state.competency_type_index
                        else ("active" if i == state.competency_type_index else "pending")
                    ),
                }
                for i, code in enumerate(COMPETENCY_TYPE_ORDER)
            ],
            "actions": [
                {"id": "skip_group", "label": "Bỏ qua nhóm này", "command": "không"},
                {"id": "exit_flow", "label": "Xem tổng kết ngay", "command": "xem tổng kết"},
            ],
        }

    def _extract_skills_from_message(self, text: str) -> list[str]:
        """Chỉ nhận skill khi match alias đã biết, hoặc khi user liệt kê có dấu phẩy.

        Bỏ fallback "token bất kỳ ≥ 2 ký tự" — tránh nuốt cả câu hỏi tự do.
        """
        skills: list[str] = []
        seen: set[str] = set()
        for name in (
            resolve_all_competency_aliases(text)
            + resolve_all_soft_skill_aliases(text)
        ):
            key = name.lower()
            if key not in seen:
                seen.add(key)
                skills.append(name)
        for subject in resolve_all_subject_aliases(text):
            for mapped in competencies_from_subject(subject):
                key = mapped.lower()
                if key not in seen:
                    seen.add(key)
                    skills.append(mapped)
        if skills:
            return skills

        # Chỉ chấp nhận liệt kê dạng có dấu phẩy / chấm phẩy / xuống dòng,
        # tokens ngắn (< 30 ký tự) và không có chữ in tiếng Việt câu hỏi.
        if "," not in text and ";" not in text and "\n" not in text:
            return skills
        for part in re.split(r"[,;、\n]+", text):
            label = part.strip()
            if not (2 <= len(label) <= 30):
                continue
            if _SKIP_RE.match(label) or _QUESTION_RE.search(_strip_diacritics(label)):
                continue
            # Không nhận tokens có khoảng trắng ≥ 4 (giống câu nói).
            if label.count(" ") >= 4:
                continue
            key = label.lower()
            if key not in seen:
                seen.add(key)
                skills.append(label)
        return skills

    @staticmethod
    def _is_skip_response(text: str) -> bool:
        t = text.strip()
        if not t:
            return True
        return bool(_SKIP_RE.match(t))

    def _handle_gap_summary(self, state: SessionState, user_text: str) -> OrchestratorTurn:
        summary, structured = self._build_gap_summary_with_card(state)
        if re.search(r"khóa|course|học\s+gì", user_text or "", re.IGNORECASE):
            state.phase = "course"
            courses_by_skill = self._courses_for_missing_structured(state)
            courses_block = self._format_courses_plain(courses_by_skill)
            intro = (
                f"**Gợi ý khóa học — {state.career or 'nghề mục tiêu'}**\n\n"
                f"Dưới đây là khóa học theo từng kỹ năng còn thiếu "
                f"({len(courses_by_skill)} kỹ năng)."
            )
            structured = {
                **structured,
                "courses_by_skill": courses_by_skill,
            }
            return OrchestratorTurn(
                handled=True,
                reply=intro + "\n\n" + courses_block,
                structured=structured,
                stop=True,
                graph={"typed_gap": True, "courses_by_skill": courses_by_skill},
            )
        return OrchestratorTurn(
            handled=True,
            reply=summary,
            structured=structured,
            stop=True,
        )

    def _build_gap_summary(self, state: SessionState) -> str:
        summary, _ = self._build_gap_summary_with_card(state)
        return summary

    def _build_gap_summary_with_card(
        self, state: SessionState
    ) -> tuple[str, dict[str, Any]]:
        by_type = apply_skills_gap_typed(state, self._graph, career=state.career)
        known_items, missing_items = merge_typed_gap_results(by_type)
        career = state.career or "nghề mục tiêu"
        lines = [
            f"**Tóm tắt khoảng cách kỹ năng — {career}**",
            "",
        ]
        if known_items:
            lines.append(
                "✅ Đã có: " + ", ".join(c.name for c in known_items[:12])
                + (" …" if len(known_items) > 12 else "")
            )
        if missing_items:
            lines.append(
                "📌 Cần học thêm: "
                + ", ".join(c.name for c in missing_items[:15])
                + (" …" if len(missing_items) > 15 else "")
            )
        else:
            lines.append("📌 Theo graph, bạn đã phủ các nhóm kỹ năng chính.")
        lines.append(
            "\nGõ «gợi ý khóa học» để xem khóa theo từng kỹ năng còn thiếu, "
            "hoặc hỏi tự do bất kỳ điều gì bạn còn băn khoăn."
        )
        structured = {
            "type": "competency_gap_summary",
            "career": career,
            "known": [c.name for c in known_items],
            "missing": [c.name for c in missing_items],
            "actions": [
                {"id": "courses", "label": "Gợi ý khóa học", "command": "gợi ý khóa học"},
                {"id": "ask_more", "label": "Hỏi thêm tự do", "command": ""},
            ],
        }
        return "\n".join(lines), structured

    def _courses_for_missing_structured(self, state: SessionState) -> list[dict[str, Any]]:
        by_type = apply_skills_gap_typed(state, self._graph, career=state.career)
        _, missing_items = merge_typed_gap_results(by_type)
        missing_labels = [c.name for c in missing_items if c.name]
        return build_courses_by_skill_blocks(
            self._graph,
            state.career or "",
            missing_labels,
        )

    @staticmethod
    def _format_courses_plain(courses_by_skill: list[dict[str, Any]]) -> str:
        if not courses_by_skill:
            return "_Chưa tìm thấy kỹ năng thiếu hoặc khóa học phù hợp trong graph._"
        lines: list[str] = []
        for block in courses_by_skill:
            skill = block.get("skill") or "Kỹ năng"
            courses = block.get("courses") or []
            if courses:
                names = ", ".join(
                    c.get("title") or c.get("course_name") or "Khóa học"
                    for c in courses[:4]
                )
                lines.append(f"- **{skill}**: {names}")
            else:
                lines.append(f"- **{skill}**: _Chưa có khóa trong đồ thị._")
        return "\n".join(lines)
