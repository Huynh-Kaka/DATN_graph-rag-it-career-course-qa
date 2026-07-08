from __future__ import annotations

import json
import logging
import uuid as uuid_mod
from typing import Any

from pydantic import ValidationError

from app.advice.schema import (
    ADVICE_RESULT_JSON_SCHEMA,
    normalize_advice_payload,
)
from app.db.enums import ROLE_DISPLAY, TargetRole, UserBackground, WeeklyTime
from app.db.profile_repository import ProfileRepository
from app.db.profile_snapshot import ProfileSnapshot
from app.generator.advisory_prompt import (
    build_advisory_system_prompt,
    build_advisory_user_prompt,
    format_advice_reply,
)
from app.graph.course_suggestions import enrich_advice_payload_courses
from app.graph.repository import GraphRepository
from app.graph.skills_gap import (
    apply_skills_gap_to_result,
    build_gap_skill_names,
    resolve_known_item_codes,
)
from app.session.competency_types import COMPETENCY_TYPE_ORDER, need_rel_for_type
from app.response.structured import plain_text_from_structured, structured_from_advice
from app.rag.graph_builder import GraphContextBuilder
from app.services.gemini_generator_client import GeminiGeneratorClient
from app.session.repository import SessionRepository, create_session_repository

logger = logging.getLogger(__name__)


class AdvisoryService:
    def __init__(
        self,
        *,
        profiles: ProfileRepository | None = None,
        sessions: SessionRepository | None = None,
        graph: GraphRepository | None = None,
        llm: GeminiGeneratorClient | None = None,
    ) -> None:
        self._profiles = profiles or ProfileRepository()
        self._sessions = sessions or create_session_repository()
        self._graph_builder = GraphContextBuilder()
        self._graph = graph or GraphRepository()
        self._llm = llm or GeminiGeneratorClient()

    async def submit_advisory_form(
        self,
        *,
        background: UserBackground,
        role: TargetRole,
        known_skills: list[str],
        goals: list[str],
        role_note: str | None = None,
        weekly_time: WeeklyTime | None = None,
        initial_question: str | None = None,
        existing_profile_id: str | None = None,
        career_label_override: str | None = None,
        existing_session_id: str | None = None,
    ) -> dict[str, Any]:
        # Form submit luôn tạo profile mới từ payload (tránh tái dùng profile cũ).
        # existing_profile_id chỉ dành cho API gắn session vào profile có sẵn (không qua form).
        if existing_profile_id:
            profile = await self._profiles.get_profile(existing_profile_id)
            if profile is None:
                raise ValueError("profile_id không tồn tại")
        else:
            profile = await self._profiles.create_profile(
                background=background,
                role=role,
                known_skills=known_skills,
                goals=goals,
                role_note=role_note,
                weekly_time=weekly_time,
                initial_question=initial_question,
                profile_completed=True,
            )

        career_label = (career_label_override or "").strip() or ROLE_DISPLAY.get(
            role.value, role.value
        )
        _incoming_sid = (existing_session_id or "").strip() or None
        session_id: str
        if _incoming_sid:
            try:
                parsed_sid = uuid_mod.UUID(_incoming_sid)
                try:
                    await self._profiles.link_session_profile(
                        _incoming_sid,
                        profile.profile_id,
                        career=career_label,
                    )
                except ValueError:
                    await self._profiles.create_session_for_profile(
                        profile.profile_id,
                        session_id=parsed_sid,
                        career=career_label,
                    )
                session_id = _incoming_sid
            except ValueError:
                session_uuid = await self._profiles.create_session_for_profile(
                    profile.profile_id,
                    career=career_label,
                )
                session_id = str(session_uuid)
        else:
            session_uuid = await self._profiles.create_session_for_profile(
                profile.profile_id,
                career=career_label,
            )
            session_id = str(session_uuid)

        state = await self._sessions.get_or_create(session_id)
        state.profile_id = profile.profile_id
        state.profile = profile
        state.career = career_label
        state.last_domain_out = False
        state.pending_message = ""
        # S2 — pre-fill known_by_type theo competency_type từ graph,
        # rồi nhảy thẳng tới gap_summary để không bắt user lặp 7 bước slot-fill.
        self._prefill_known_by_type(state, profile.known_skills, career_label)
        state.phase = "gap_summary"
        state.competency_type_index = len(COMPETENCY_TYPE_ORDER)
        await self._sessions.save(state)

        advice_payload, reply_text = await self._generate_and_store_advice(
            session_id=session_id,
            profile=profile,
            career_label=career_label,
        )
        advice_payload = normalize_advice_payload(advice_payload, raw_response=reply_text)

        structured = structured_from_advice(
            advice_payload,
            career=career_label,
            known_skills=list(profile.known_skills),
        )
        reply_for_chat = plain_text_from_structured(structured) or reply_text
        if not self._assistant_reply_exists(state, reply_for_chat):
            await self._sessions.append_message(state, "assistant", reply_for_chat)
        await self._sessions.save(state)

        return {
            "profile_id": profile.profile_id,
            "session_id": session_id,
            "reply": reply_for_chat,
            "structured": structured.model_dump_public(),
            "advice": advice_payload,
            "session": state.to_public_dict(),
        }

    @staticmethod
    def _assistant_reply_exists(state: Any, content: str) -> bool:
        text = (content or "").strip()
        if not text:
            return True
        for turn in reversed(state.messages):
            if turn.role == "assistant":
                return turn.content.strip() == text
        return False

    async def get_cached_advice(self, session_id: str) -> dict[str, Any] | None:
        raw = await self._profiles.get_latest_advice(session_id)
        if raw is None:
            return None
        return normalize_advice_payload(raw)

    def search_careers(self, query: str, *, limit: int = 6) -> dict[str, Any]:
        return self._graph.search_careers(query, limit=limit)

    def _prefill_known_by_type(
        self,
        state: Any,
        known_skills: list[str],
        career_label: str,
    ) -> None:
        """Map form known_skills → known_by_type bucket per competency type."""
        if not known_skills or not career_label:
            return
        for type_code in COMPETENCY_TYPE_ORDER:
            rel = need_rel_for_type(type_code)
            if not rel:
                continue
            try:
                pf = self._graph.pathfinding_by_type(career_label, rel)
            except Exception:  # graph có thể fail mềm — không chặn form submit
                continue
            if not pf.found or not pf.competencies:
                continue
            known_codes = resolve_known_item_codes(
                known_skills, competency_catalog=pf.competencies
            )
            if not known_codes:
                continue
            matched = [
                c.name
                for c in pf.competencies
                if c.code and c.code in known_codes and c.name
            ]
            if matched:
                state.record_known_for_type(type_code, matched)

    async def _generate_and_store_advice(
        self,
        *,
        session_id: str,
        profile: ProfileSnapshot,
        career_label: str,
    ) -> tuple[dict[str, Any], str]:
        graph_lines = self._graph_builder.get_graph_context(target_role=career_label)

        cached = await self._profiles.get_latest_advice(session_id)
        if cached and cached.get("skills_gap"):
            cached = normalize_advice_payload(cached)
            reply = format_advice_reply(cached)
            return cached, reply

        llm_raw = await self._call_structured_llm(profile, graph_context=graph_lines)
        structured = normalize_advice_payload(llm_raw)
        structured = enrich_advice_payload_courses(
            structured,
            self._graph,
            career_label,
            known_skills=list(profile.known_skills),
        )
        reply_text = format_advice_reply(structured)

        advice_id = await self._profiles.save_advice(
            session_id=session_id,
            profile_id=profile.profile_id,
            skills_gap=structured.get("skills_gap"),
            roadmap=structured.get("roadmap"),
            recommended_courses=structured.get("recommended_courses"),
            estimated_months=structured.get("estimated_months"),
            raw_response=structured.get("summary_vi") or reply_text,
        )
        payload = {
            "id": advice_id,
            "session_id": session_id,
            "profile_id": profile.profile_id,
            "skills_gap": structured.get("skills_gap"),
            "roadmap": structured.get("roadmap"),
            "recommended_courses": structured.get("recommended_courses"),
            "estimated_months": structured.get("estimated_months"),
        }
        return payload, reply_text

    async def _call_structured_llm(
        self, profile: ProfileSnapshot, *, graph_context: list[str]
    ) -> dict[str, Any]:
        if not self._llm.available:
            return self._fallback_advice(profile)

        system = build_advisory_system_prompt()
        user = build_advisory_user_prompt(profile, graph_context=graph_context)

        try:
            text = self._llm.generate_json(
                system_prompt=system,
                user_prompt=user,
                response_schema=ADVICE_RESULT_JSON_SCHEMA,
            )
            if not text:
                raise ValueError("LLM trả về rỗng")
            return json.loads(text)
        except (json.JSONDecodeError, RuntimeError, ValueError, ValidationError) as exc:
            logger.warning("Structured advisory LLM failed: %s", exc)
            return self._fallback_advice(profile)
        except Exception as exc:
            logger.warning("Structured advisory LLM unavailable: %s", exc)
            return self._fallback_advice(profile)

    def _fallback_advice(self, profile: ProfileSnapshot) -> dict[str, Any]:
        role = profile.target_role_label
        career = role
        pf = self._graph.pathfinding(career, known_skills=list(profile.known_skills))
        missing, weak = build_gap_skill_names(pf)

        if pf.career_name:
            role = pf.career_name

        roadmap = _fallback_roadmap(role, missing)
        summary_missing = ", ".join(missing[:5]) if missing else ""
        if missing:
            summary_vi = (
                f"Dựa trên hồ sơ và đồ thị nghề «{role}», bạn nên ưu tiên các kỹ năng còn thiếu"
                f" như {summary_missing}. Lộ trình gợi ý theo tháng bên dưới; "
                f"hỏi tiếp để nhận gợi ý khóa học cụ thể."
            )
        else:
            summary_vi = (
                f"Dựa trên hồ sơ của bạn (mục tiêu {role}), hãy tập trung lấp khoảng cách kỹ năng "
                f"theo lộ trình từng tháng. Bạn có thể hỏi tiếp về khóa học cụ thể hoặc kỹ năng chi tiết."
            )

        return {
            "skills_gap": {"missing": missing, "weak": weak},
            "roadmap": roadmap,
            "recommended_courses": [],
            "estimated_months": max(len(roadmap), 6),
            "summary_vi": summary_vi,
        }


def _fallback_roadmap(role: str, missing: list[str]) -> list[dict[str, Any]]:
    months = 6
    if missing:
        chunk = max(1, (len(missing) + months - 1) // months)
        topics_by_month: list[list[str]] = []
        for i in range(months):
            start = i * chunk
            slice_topics = missing[start : start + chunk]
            if slice_topics:
                topics_by_month.append(slice_topics)
            elif i == 0:
                topics_by_month.append(["Nền tảng " + role])
        while len(topics_by_month) < months:
            topics_by_month.append(["Ôn tập & mở rộng"])
    else:
        topics_by_month = [
            ["Nền tảng " + role, "Git", "Một ngôn ngữ chính"],
            ["API / framework", "Deploy cơ bản"],
            ["Project thực hành", "Testing cơ bản"],
            ["DevOps / CI nhẹ", "Documentation"],
            ["Portfolio & CV", "Mock interview"],
            ["Ứng tuyển & networking"],
        ]

    milestones = [
        "Hoàn thành 1 project nhỏ liên quan " + role,
        "Project có README và demo",
        "Project có test cơ bản",
        "Pipeline build/deploy đơn giản",
        "Portfolio online với 2+ project",
        "Sẵn sàng phỏng vấn junior",
    ]
    return [
        {
            "month": i + 1,
            "topics": topics,
            "milestone": milestones[min(i, len(milestones) - 1)],
            "courses": [],
        }
        for i, topics in enumerate(topics_by_month[:months])
    ]
