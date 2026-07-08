from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.profile_repository import ProfileRepository
from app.generator.response_generator import ResponseGenerator
from app.graph.formatters import format_competency_relation
from app.graph.repository import GraphRepository
from app.graph.subject_career_case_study import (
    format_subject_career_reply,
    log_case_study_sample,
)
from app.rag.aliases import resolve_subject_alias, subject_search_terms
from app.intent.competency_scope import (
    detect_competency_type_scope,
    need_rel_for_scope,
    scope_label_vi,
)
from app.intent.models import RouteOutcome
from app.intent.router import IntentRouterService
from app.intent.templates import (
    CHAT_GREETING,
    OUT_OF_DOMAIN_MESSAGE,
    greeting_message,
    suggest_form_message,
)
from app.rag.exemplar import ExemplarRetriever
from app.rag.fusion import (
    FusionService,
    extract_relevant_ids_from_graph,
    map_hits_to_graph_nodes,
)
from app.rag.retriever import VectorRetriever
from app.response.api_shape import shape_chat_response
from app.response.structured import (
    plain_text_from_structured,
    structured_from_competency_card,
    structured_from_course_rec,
    structured_from_gap_courses,
    structured_from_gap_summary,
    structured_from_pathfinding,
)
from app.services.competency_orchestrator import CompetencyTypeOrchestrator
from app.services.roadmap_followup import RoadmapFollowupService
from app.session.context import (
    apply_route_to_state,
    build_router_user_message,
    is_bulk_missing_courses_request,
)
from app.session.followup import _FREE_QUESTION_RE, _strip_diacritics, maybe_adjust_outcome
from app.session.repository import SessionRepository, create_session_repository
from app.session.store import SessionState

logger = logging.getLogger(__name__)

_WANTS_IT_ADVICE = re.compile(
    r"tư\s*vấn|muốn\s+(được\s+)?(tư\s*vấn|học|biết)|giúp\s+(mình|tôi|em)|"
    r"hướng\s*nghiệp|điền\s*form|ngành\s+này|lĩnh\s*vực\s+này|"
    r"được\s+không|hướng\s*dẫn|lộ\s*trình|quan\s+tâm\s+ngành",
    re.IGNORECASE,
)


class ChatService:
    def __init__(
        self,
        *,
        sessions: SessionRepository | None = None,
        router: IntentRouterService | None = None,
        graph: GraphRepository | None = None,
        generator: ResponseGenerator | None = None,
        roadmap: RoadmapFollowupService | None = None,
        profiles: ProfileRepository | None = None,
        retriever: VectorRetriever | None = None,
        fusion: FusionService | None = None,
        exemplars: ExemplarRetriever | None = None,
    ) -> None:
        self._sessions = sessions or create_session_repository()
        self._router = router or IntentRouterService()
        self._graph = graph or GraphRepository()
        self._generator = generator or ResponseGenerator()
        self._roadmap = roadmap or RoadmapFollowupService(
            graph=self._graph, profiles=profiles or ProfileRepository()
        )
        self._competency_flow = CompetencyTypeOrchestrator(graph=self._graph)
        self._profiles = profiles or ProfileRepository()
        self._retriever = retriever or VectorRetriever()
        self._fusion = fusion or FusionService()
        self._exemplars = exemplars or ExemplarRetriever()

    @staticmethod
    def greeting() -> str:
        return CHAT_GREETING

    async def get_session(self, session_id: str | None) -> dict:
        state = await self._sessions.get_or_create(session_id)
        return state.to_public_dict()

    async def get_history(self, session_id: str, *, limit: int = 50) -> dict:
        if await self._session_hidden_by_filter(session_id):
            created_after = settings.session_filter_after
            return {
                "session_id": session_id,
                "messages": [],
                "history_hidden": True,
                "filter_after": created_after.isoformat() if created_after else None,
            }
        messages = await self._sessions.list_messages(session_id, limit=limit)
        return {"session_id": session_id, "messages": messages}

    @staticmethod
    def _as_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    async def _session_hidden_by_filter(self, session_id: str) -> bool:
        created_after = settings.session_filter_after
        if created_after is None:
            return False
        created_at = await self._sessions.session_created_at(session_id)
        if created_at is None:
            return False
        return self._as_utc(created_at) < self._as_utc(created_after)

    async def _resolve_session_id(self, session_id: str | None) -> str | None:
        sid = (session_id or "").strip()
        if not sid:
            return None
        if await self._session_hidden_by_filter(sid):
            logger.info(
                "Session %s before SESSION_FILTER_AFTER; starting new session",
                sid,
            )
            return None
        return sid

    async def list_sessions(self, *, limit: int = 20) -> dict:
        created_after = settings.session_filter_after
        sessions = await self._sessions.list_sessions(
            limit=limit,
            created_after=created_after,
        )
        out: dict[str, Any] = {"sessions": sessions}
        if created_after is not None:
            out["filter_after"] = created_after.isoformat()
        return out

    async def handle_message(
        self, *, message: str, session_id: str | None, is_retry: bool = False
    ) -> dict:
        session_id = await self._resolve_session_id(session_id)
        state = await self._sessions.get_or_create(session_id)
        if not state.career and state.profile and state.profile.target_role_label:
            state.career = state.profile.target_role_label
        text = (message or "").strip()
        if not text:
            return {
                "session_id": state.session_id,
                "reply": "Bạn muốn hỏi về nghề IT hay kỹ năng nào?",
                "action": None,
                "structured": None,
                "session": state.to_public_dict(),
            }

        if state.last_domain_out and self._wants_it_advice(text):
            state.pending_message = text
            await self._sessions.append_message(state, "user", text)
            reply = suggest_form_message()
            await self._sessions.append_message(state, "assistant", reply)
            await self._sessions.save(state)
            return {
                "session_id": state.session_id,
                "reply": reply,
                "action": "suggest_form",
                "form_url": f"/form.html?session_id={state.session_id}",
                "structured": None,
                "session": state.to_public_dict(),
            }

        result = await self._process_turn(state, text, skip_user_append=is_retry)
        result = self._finalize_llm_meta(result)
        route_meta = self._route_meta_from_result(result)
        if result.get("is_error"):
            route_meta = {**(route_meta or {}), "intent": "_system_error", "is_error": True}
        message_id = await self._sessions.append_message(
            state,
            "assistant",
            result["reply"],
            route_meta=route_meta,
        )
        await self._sessions.save(state)
        return shape_chat_response({
            **result,
            "message_id": message_id,
            "session": state.to_public_dict(),
        })

    async def _process_turn(
        self, state: SessionState, text: str, *, skip_user_append: bool = False
    ) -> dict:
        if not skip_user_append:
            await self._sessions.append_message(state, "user", text)

        router_prompt = build_router_user_message(state, text)
        outcome = self._router.route(text, user_prompt=router_prompt, state=state)
        outcome = maybe_adjust_outcome(state, text, outcome)
        prev_career = state.career
        apply_route_to_state(state, outcome.route)
        await self._sessions.save(state)

        if outcome.route.domain == "out":
            state.last_domain_out = True
            state.pending_message = text
            await self._sessions.save(state)
            return {
                "session_id": state.session_id,
                "reply": OUT_OF_DOMAIN_MESSAGE,
                "action": None,
                "structured": None,
                "route": outcome.route.model_dump(),
            }

        state.last_domain_out = False

        if outcome.stop:
            reply = outcome.reply or greeting_message()
            if outcome.route.intent == "slot_fill" and not outcome.is_error:
                reply = self._generator.slot_fill(
                    user_message=text,
                    route=outcome.route,
                    state=state,
                    fallback=reply,
                )
            return {
                "session_id": state.session_id,
                "reply": reply,
                "action": None,
                "structured": None,
                "route": outcome.route.model_dump(),
                "is_error": outcome.is_error,
            }

        return await self._answer_from_intent(state, text, outcome, prev_career=prev_career)

    async def _answer_from_intent(
        self,
        state: SessionState,
        message: str,
        outcome: RouteOutcome,
        *,
        prev_career: str | None = None,
    ) -> dict:
        intent = outcome.route.intent
        route_dump = outcome.route.model_dump()
        route_confidence = outcome.route.confidence

        if intent == "roadmap_followup":
            payload = await self._roadmap.build(state, user_message=message)
            graph = payload.get("graph")
            evidence = self._fusion.build_evidence(
                graph_payload=graph if isinstance(graph, dict) else None,
                vector_docs=[],
            )
            return {
                "session_id": state.session_id,
                "reply": payload["reply"],
                "structured": payload.get("structured"),
                "route": self._enrich_route(route_dump, graph),
                "graph": graph,
                "advice_id": payload.get("advice_id"),
                "evidence": evidence,
            }

        if intent == "subject_career":
            return self._answer_subject_career(
                state, message, outcome, route_dump=route_dump
            )

        doc_type = "course" if intent == "course_rec" else "career"
        if intent not in ("pathfinding", "course_rec"):
            doc_type = None
        vector_docs = self._retriever.retrieve_docs(
            message, top_k=3, doc_type=doc_type
        )
        # A-01 tight fusion: gom vector hits → seed node ids cho Cypher.
        seed_map = map_hits_to_graph_nodes(vector_docs)
        exemplar_texts = await self._exemplars.fetch_examples(message, top_k=2)

        # Delegate orchestrator khi đang slot-fill hoặc gap_summary/course + gợi ý khóa tổng hợp.
        _bulk_courses = (
            intent == "course_rec"
            and state.phase in ("gap_summary", "course")
            and is_bulk_missing_courses_request(message)
        )
        if (
            state.career
            and state.phase in ("collecting", "gap_summary", "course")
            and (intent in ("slot_fill", "competency_slot_fill") or _bulk_courses)
        ):
            if (
                self._competency_flow.should_handle(state)
                or state.phase in ("gap_summary", "course")
            ):
                orch = self._competency_flow.handle_turn(state, message)
                if orch.handled and orch.reply:
                    await self._sessions.save(state)
                    return {
                        "session_id": state.session_id,
                        "reply": orch.reply,
                        "structured": self._wrap_orchestrator_structured(
                            orch.structured, orch.reply
                        ),
                        "route": {**route_dump, "intent": "competency_slot_fill"},
                        "graph": orch.graph,
                    }

        if intent == "competency_slot_fill":
            orch = self._competency_flow.handle_turn(state, message)
            reply: str | None = None
            orch_structured: dict[str, Any] | None = None
            if not orch.handled:
                # Orchestrator từ chối (vd: detected câu hỏi tự do).
                # Không reset, không trả prompt — fall xuống các handler khác bên dưới.
                pass
            elif orch.reply:
                reply = orch.reply
                orch_structured = orch.structured
            elif state.career and self._competency_flow_not_started(state):
                reply, orch_structured = self._competency_flow.start_collection_with_card(state)
            if reply is not None:
                await self._sessions.save(state)
                return {
                    "session_id": state.session_id,
                    "reply": reply,
                    "structured": self._wrap_orchestrator_structured(orch_structured, reply),
                    "route": {**route_dump, "intent": "competency_slot_fill"},
                    "graph": orch.graph,
                }

        if intent == "pathfinding":
            career = (
                outcome.route.entities.career
                or state.career
                or state.target_role
                or message[:120]
            )
            career_str = str(career)
            looks_like_question = bool(
                _FREE_QUESTION_RE.search(_strip_diacritics(message or ""))
            )
            career_switched = self._is_explicit_new_career(prev_career, career_str)
            if (
                state.phase == "collecting"
                and career_switched
                and not looks_like_question
            ):
                state.career = career_str
                intro, card = self._competency_flow.start_collection_with_card(state)
                await self._sessions.save(state)
                return {
                    "session_id": state.session_id,
                    "reply": intro,
                    "structured": self._wrap_orchestrator_structured(card, intro),
                    "route": {**route_dump, "intent": "competency_slot_fill"},
                }
            if career_switched and state.phase in ("gap_summary", "course"):
                state.known_by_type = {}
                state.competency_type_index = 0
                state.phase = "idle"
                state.career = career_str
            known = list(state.profile.known_skills) if state.profile else None
            session_known = state.all_known_skills()
            if session_known:
                known = list(known or []) + [
                    s for s in session_known if s not in (known or [])
                ]
            type_scope = detect_competency_type_scope(
                message,
                competency_entity=outcome.route.entities.competency,
            )
            rel_scope = need_rel_for_scope(type_scope)
            if rel_scope:
                pf = self._graph.pathfinding_by_type(
                    str(career),
                    rel_scope,
                    known_skills=known,
                    seed_career_codes=seed_map.get("career_codes"),
                    seed_competency_codes=seed_map.get("competency_codes"),
                )
            else:
                pf = self._graph.pathfinding(
                    str(career),
                    known_skills=known,
                    seed_career_codes=seed_map.get("career_codes"),
                    seed_competency_codes=seed_map.get("competency_codes"),
                )
            graph_dump = pf.model_dump()
            relevant_ids = extract_relevant_ids_from_graph(graph_dump)
            if relevant_ids:
                vector_docs = self._retriever.retrieve_docs(
                    message,
                    top_k=3,
                    doc_type=doc_type,
                    relevant_ids=relevant_ids,
                )
            fused = self._fusion.aggregate(
                graph_payload=graph_dump,
                vector_docs=vector_docs,
                graph_seed_ids=seed_map,
            )
            scope_label = scope_label_vi(type_scope)
            reply = self._generator.pathfinding(
                user_message=message,
                result=pf,
                state=state,
                vector_context=fused["context_block"],
                exemplars=exemplar_texts,
                route_confidence=route_confidence,
                competency_scope_label=scope_label,
            )
            structured = structured_from_pathfinding(
                pf,
                summary=reply,
                career=str(career),
                scope_label=scope_label,
            )
            return {
                "session_id": state.session_id,
                "reply": plain_text_from_structured(structured) or reply,
                "structured": structured.model_dump_public(),
                "route": self._enrich_route(route_dump, graph_dump),
                "graph": graph_dump,
                "evidence": fused["evidence"],
            }

        if intent == "course_rec":
            competency = outcome.route.entities.competency or state.competency or message
            cr = self._graph.course_recommendation(
                str(competency),
                seed_course_codes=seed_map.get("course_codes"),
            )
            graph_dump = cr.model_dump()
            relevant_ids = extract_relevant_ids_from_graph(graph_dump)
            if relevant_ids:
                vector_docs = self._retriever.retrieve_docs(
                    message,
                    top_k=3,
                    doc_type=doc_type,
                    relevant_ids=relevant_ids,
                )
            fused = self._fusion.aggregate(
                graph_payload=graph_dump,
                vector_docs=vector_docs,
                graph_seed_ids=seed_map,
            )
            reply = self._generator.course_rec(
                user_message=message,
                result=cr,
                state=state,
                vector_context=fused["context_block"],
                exemplars=exemplar_texts,
                route_confidence=route_confidence,
            )
            structured = structured_from_course_rec(cr, summary=reply)
            return {
                "session_id": state.session_id,
                "reply": plain_text_from_structured(structured) or reply,
                "structured": structured.model_dump_public(),
                "route": self._enrich_route(route_dump, graph_dump),
                "graph": graph_dump,
                "evidence": fused["evidence"],
            }

        if intent == "competency_relation":
            competency = outcome.route.entities.competency or state.competency or message
            rel = self._graph.competency_relations(str(competency))
            graph_dump = rel.model_dump()
            static = format_competency_relation(rel)
            if rel.coverage != "full":
                return {
                    "session_id": state.session_id,
                    "reply": static,
                    "structured": None,
                    "route": self._enrich_route(route_dump, graph_dump),
                    "graph": graph_dump,
                    "evidence": {},
                }
            vector_docs = self._retriever.retrieve_docs(
                message, top_k=3, doc_type="competency"
            )
            fused = self._fusion.aggregate(
                graph_payload=graph_dump,
                vector_docs=vector_docs,
                graph_seed_ids=seed_map,
            )
            reply = self._generator.competency_relation(
                user_message=message,
                result=rel,
                state=state,
                vector_context=fused["context_block"],
                route_confidence=route_confidence,
            )
            return {
                "session_id": state.session_id,
                "reply": reply or static,
                "structured": None,
                "route": self._enrich_route(route_dump, graph_dump),
                "graph": graph_dump,
                "evidence": fused["evidence"],
            }

        fallback = outcome.reply or greeting_message()
        reply = self._generator.slot_fill(
            user_message=message,
            route=outcome.route,
            state=state,
            fallback=fallback,
        )
        return {
            "session_id": state.session_id,
            "reply": reply,
            "structured": None,
            "route": route_dump,
        }

    def _answer_subject_career(
        self,
        state: SessionState,
        message: str,
        outcome: RouteOutcome,
        *,
        route_dump: dict[str, Any],
    ) -> dict[str, Any]:
        """C-03: Subject → Course → Competency → Career."""
        subject_key = (
            outcome.route.entities.subject
            or resolve_subject_alias(message)
            or message[:120]
        )
        rows = self._graph.subject_to_careers(str(subject_key))
        log_case_study_sample(rows, logger=logger)

        terms = subject_search_terms(str(subject_key))
        label = terms[0] if terms else str(subject_key)
        reply = format_subject_career_reply(
            rows,
            subject_label=label,
            query_term=label,
        )
        graph_payload = {
            "subject_query": str(subject_key),
            "subject_label": label,
            "subject_career_paths": rows,
        }
        return {
            "session_id": state.session_id,
            "reply": reply,
            "structured": None,
            "route": self._enrich_route(route_dump, graph_payload),
            "graph": graph_payload,
            "evidence": {},
        }

    def _finalize_llm_meta(self, result: dict[str, Any]) -> dict[str, Any]:
        """Gắn backend LLM đã dùng (cho debug / paper / ablation)."""
        out = dict(result)
        backend = self._generator.last_generator_backend
        if backend:
            out["generator_backend"] = backend
        elif "generator_backend" not in out:
            out["generator_backend"] = "template_or_rule"
        out["llm_router"] = "gemini"
        gen_is_error = getattr(self._generator, "last_is_error", False)
        if out.get("is_error") or gen_is_error:
            out["is_error"] = True
        else:
            out.setdefault("is_error", False)
        return out

    @staticmethod
    def _wrap_orchestrator_structured(
        card: dict[str, Any] | None, reply: str | None
    ) -> dict[str, Any] | None:
        """Đóng gói dict do orchestrator trả ra thành StructuredReply cho FE."""
        if not isinstance(card, dict):
            return None
        kind = card.get("type")
        if kind == "competency_collection":
            return structured_from_competency_card(card).model_dump_public()
        if kind == "competency_gap_summary":
            courses = card.get("courses_by_skill")
            if courses:
                return structured_from_gap_courses(
                    card, courses, summary=reply
                ).model_dump_public()
            return structured_from_gap_summary(card, summary=reply).model_dump_public()
        return None

    @staticmethod
    def _enrich_route(route: dict[str, Any], graph: dict[str, Any] | None) -> dict[str, Any]:
        if graph is None:
            return route
        enriched = dict(route)
        enriched["graph_snapshot"] = graph
        return enriched

    @staticmethod
    def _wants_it_advice(text: str) -> bool:
        return bool(_WANTS_IT_ADVICE.search(text))

    @staticmethod
    def _competency_flow_not_started(state: SessionState) -> bool:
        return state.competency_type_index == 0 and not state.known_by_type

    @staticmethod
    def _is_explicit_new_career(prev_career: str | None, career: str) -> bool:
        prev = (prev_career or "").strip().casefold()
        new = (career or "").strip().casefold()
        return bool(new) and bool(prev) and prev != new

    @staticmethod
    def _route_meta_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
        route = result.get("route")
        if not isinstance(route, dict):
            return None
        graph = result.get("graph")
        if isinstance(graph, dict):
            route = {**route, "graph_snapshot": graph}
        return {
            "intent": route.get("intent"),
            "domain": route.get("domain"),
            "route": route,
        }
