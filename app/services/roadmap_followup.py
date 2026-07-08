"""
roadmap_followup — kết hợp advice_results + skills gap (Neo4j) + course_rec theo skill thiếu.
"""

from __future__ import annotations

from typing import Any

from app.advice.schema import normalize_advice_payload, normalize_skills_gap
from app.db.profile_repository import ProfileRepository
from app.graph.course_suggestions import build_courses_by_skill_blocks
from app.graph.models import PathfindingResult
from app.graph.repository import GraphRepository
from app.graph.skills_gap import (
    apply_skills_gap_typed,
    build_gap_skill_names,
    merge_typed_gap_results,
    pathfinding_from_typed_gap,
)
from app.response.structured import (
    StructuredReply,
    StructuredSection,
    plain_text_from_structured,
)
from app.session.store import SessionState
from app.utils.skill_normalize import normalize_skill_label, normalize_skill_set

_MAX_COURSES_PER_SKILL = 4


class RoadmapFollowupService:
    def __init__(
        self,
        *,
        profiles: ProfileRepository | None = None,
        graph: GraphRepository | None = None,
    ) -> None:
        self._profiles = profiles or ProfileRepository()
        self._graph = graph or GraphRepository()

    async def build(
        self,
        state: SessionState,
        *,
        user_message: str,
    ) -> dict[str, Any]:
        career = (
            state.career
            or (state.profile.target_role_label if state.profile else "")
            or ""
        )
        known_codes = list(state.profile.known_skills) if state.profile else []
        session_known = state.all_known_skills()
        merged_known = self._merge_known_codes(known_codes, session_known)
        advice = await self._profiles.get_latest_advice(state.session_id)
        if advice:
            advice = normalize_advice_payload(advice)

        gap_state = SessionState(session_id=state.session_id, career=career)
        gap_state.known_by_type = dict(state.known_by_type)
        by_type = apply_skills_gap_typed(
            gap_state,
            self._graph,
            career=career,
            extra_known=merged_known or None,
        )
        pf = pathfinding_from_typed_gap(by_type, career_name=career)
        known_labels, missing_labels, weak_labels = self._merge_gap_labels(
            pf, advice, known_codes
        )

        roadmap = (advice or {}).get("roadmap") or []
        estimated = (advice or {}).get("estimated_months")
        summary = self._pick_summary(advice, career, missing_labels)

        courses_by_skill = self._fetch_courses_for_skills(career, missing_labels)

        structured = StructuredReply(
            title=f"Lộ trình & khóa học — {career or 'mục tiêu của bạn'}",
            sections=[
                StructuredSection(type="summary", text=summary),
                StructuredSection(
                    type="skills_gap",
                    title="Phân tích khoảng cách kỹ năng",
                    chips_known=known_labels,
                    chips_missing=missing_labels,
                    chips_weak=weak_labels,
                    career=pf.career_name or career,
                ),
                StructuredSection(
                    type="timeline",
                    title="Lộ trình theo tháng",
                    timeline=roadmap,
                    estimated_months=estimated,
                ),
                StructuredSection(
                    type="courses_by_skill",
                    title="Khóa học theo kỹ năng cần học",
                    courses_by_skill=courses_by_skill,
                ),
                StructuredSection(
                    type="meta",
                    estimated_months=estimated,
                    career=pf.career_name or career,
                ),
            ],
        )

        reply = plain_text_from_structured(structured)
        return {
            "reply": reply,
            "structured": structured.model_dump_public(),
            "graph": {
                "pathfinding": pf.model_dump(),
                "courses_by_skill": courses_by_skill,
            },
            "advice_id": (advice or {}).get("id"),
        }

    def _fetch_courses_for_skills(
        self, career: str, missing_labels: list[str]
    ) -> list[dict[str, Any]]:
        return build_courses_by_skill_blocks(
            self._graph,
            career,
            missing_labels,
            max_per_skill=_MAX_COURSES_PER_SKILL,
        )

    @staticmethod
    def _merge_known_codes(
        profile_codes: list[str], session_labels: list[str]
    ) -> list[str]:
        out = list(profile_codes or [])
        seen = {str(c).strip().lower() for c in out if c}
        for label in session_labels or []:
            key = str(label).strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(label)
        return out

    @staticmethod
    def _merge_gap_labels(
        pf: PathfindingResult,
        advice: dict[str, Any] | None,
        known_codes: list[str],
    ) -> tuple[list[str], list[str], list[str]]:
        known_from_graph = [c.name for c in pf.skills_known]
        missing_from_graph = [c.name for c in pf.skills_missing]

        gap = normalize_skills_gap((advice or {}).get("skills_gap"))
        advice_missing = list(gap.get("missing") or [])
        advice_weak = list(gap.get("weak") or [])

        from app.response.structured import _labels_from_form_codes

        known_display = _dedupe_labels(
            known_from_graph,
            _labels_from_form_codes(known_codes),
        )
        known_keys = normalize_skill_set(known_display)

        missing_raw = _dedupe_labels(missing_from_graph, advice_missing)
        missing_display = [
            label
            for label in missing_raw
            if normalize_skill_label(label) not in known_keys
        ]
        missing_keys = normalize_skill_set(missing_display)

        weak_raw = _dedupe_labels(advice_weak)
        weak_display = [
            label
            for label in weak_raw
            if normalize_skill_label(label) not in known_keys
            and normalize_skill_label(label) not in missing_keys
        ]

        return known_display, missing_display, weak_display

    @staticmethod
    def _pick_summary(
        advice: dict[str, Any] | None,
        career: str,
        missing: list[str],
    ) -> str:
        if advice and advice.get("raw_response"):
            raw = str(advice["raw_response"]).strip()
            if raw:
                return raw[:1200]
        if missing:
            preview = ", ".join(missing[:5])
            more = f" và {len(missing) - 5} kỹ năng khác" if len(missing) > 5 else ""
            return (
                f"Dựa trên hồ sơ và đồ thị nghề {career or 'IT'}, "
                f"bạn nên tập trung lấp các kỹ năng: {preview}{more}. "
                f"Dưới đây là lộ trình đã lưu và gợi ý khóa học theo từng kỹ năng còn thiếu."
            )
        return (
            "Dưới đây là tóm tắt lộ trình và khóa học dựa trên hồ sơ và dữ liệu đồ thị nghề nghiệp."
        )


def _label_key(label: str) -> str:
    return normalize_skill_label(label)


def _dedupe_labels(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for item in group:
            label = str(item).strip()
            if not label:
                continue
            key = _label_key(label)
            if key in seen:
                continue
            seen.add(key)
            out.append(label)
    return out

