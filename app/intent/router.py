from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.intent.career_matcher import CareerMatcher
from app.intent.career_registry import CareerRegistry
from app.intent.competency_relation_detect import (
    has_relation_signal,
    looks_like_competency_relation_question,
    pick_anchor_competency,
    should_route_competency_relation,
)
from app.intent.models import IntentRouteResult, RouteOutcome
from app.intent.parser import fallback_route, parse_route_json
from app.intent.prompt import build_router_system_prompt, build_router_user_prompt
from app.intent.templates import (
    greeting_message,
    low_confidence_message,
    out_of_domain_message,
)
from app.rag.aliases import (
    looks_like_subject_career_question,
    resolve_subject_alias,
    subject_search_terms,
)
from app.services.gemini_router_client import GeminiRouterClient
from app.services.llm_errors import normalize_llm_error_message

from app.session.store import SessionState

logger = logging.getLogger(__name__)


class IntentRouterService:
    def __init__(
        self,
        *,
        registry: CareerRegistry | None = None,
        llm: GeminiRouterClient | None = None,
    ) -> None:
        self._registry = registry or CareerRegistry()
        self._llm = llm or GeminiRouterClient()

    def route(
        self,
        message: str,
        *,
        user_prompt: str | None = None,
        state: SessionState | None = None,
    ) -> RouteOutcome:
        text = (message or "").strip()
        if not text:
            return RouteOutcome(
                route=fallback_route(),
                reply="Bạn muốn hỏi về nghề nghiệp IT hay khóa học kỹ năng nào?",
                stop=True,
                parse_fallback=True,
            )

        careers = self._registry.list_careers()
        parse_fallback = False

        subject_outcome = self._try_subject_career_route(text)
        if subject_outcome is not None:
            return subject_outcome

        rel_outcome = self._try_competency_relation_route(text, state=state)
        if rel_outcome is not None:
            return rel_outcome

        try:
            raw = self._llm.classify(
                system_prompt=build_router_system_prompt(careers),
                user_message=user_prompt or build_router_user_prompt(text),
            )
            route = parse_route_json(raw)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Intent JSON parse failed: %s", exc)
            route = fallback_route()
            parse_fallback = True
        except Exception as exc:
            logger.exception("Intent router LLM failed")
            return RouteOutcome(
                route=fallback_route(),
                reply=normalize_llm_error_message(exc),
                stop=True,
                parse_fallback=True,
                is_error=True,
            )

        outcome = self._post_process(route, careers=careers, parse_fallback=parse_fallback)
        return outcome

    def _post_process(
        self,
        route: IntentRouteResult,
        *,
        careers: list[str],
        parse_fallback: bool,
    ) -> RouteOutcome:
        if route.domain == "out":
            return RouteOutcome(
                route=route,
                reply=out_of_domain_message(),
                stop=True,
                parse_fallback=parse_fallback,
            )

        if route.confidence == "low":
            return RouteOutcome(
                route=route,
                reply=low_confidence_message(route.intent),
                stop=True,
                parse_fallback=parse_fallback,
            )

        matcher = CareerMatcher(careers)
        career_normalized = False
        raw_career = route.entities.career

        if raw_career:
            matched = matcher.resolve(raw_career)
            if matched:
                route.entities.career = matched
                career_normalized = matched != raw_career
            else:
                route.intent = "slot_fill"
                route.entities.career = None
                route.confidence = "low"
                if "career" not in route.missing_slots:
                    route.missing_slots.append("career")
                return RouteOutcome(
                    route=route,
                    reply=low_confidence_message("slot_fill"),
                    stop=True,
                    parse_fallback=parse_fallback,
                    career_normalized=False,
                )

        route.missing_slots = self._sanitize_missing_slots(route)

        if route.intent == "slot_fill":
            reply = (
                self._missing_slots_prompt(route)
                if route.missing_slots
                else greeting_message()
            )
            return RouteOutcome(
                route=route,
                reply=reply,
                stop=True,
                parse_fallback=parse_fallback,
                career_normalized=career_normalized,
            )

        if self._should_stop_for_missing_slots(route):
            reply = self._missing_slots_prompt(route)
            return RouteOutcome(
                route=route,
                reply=reply,
                stop=True,
                parse_fallback=parse_fallback,
                career_normalized=career_normalized,
            )

        return RouteOutcome(
            route=route,
            reply=None,
            stop=False,
            parse_fallback=parse_fallback,
            career_normalized=career_normalized,
        )

    @staticmethod
    def _sanitize_missing_slots(route: IntentRouteResult) -> list[str]:
        missing = list(route.missing_slots or [])
        if route.intent in ("pathfinding", "roadmap_followup"):
            return [s for s in missing if s == "career"]
        if route.intent == "course_rec":
            return [s for s in missing if s == "competency"]
        if route.intent in ("competency_slot_fill", "subject_career", "competency_relation"):
            return []
        return missing

    @staticmethod
    def _should_stop_for_missing_slots(route: IntentRouteResult) -> bool:
        if route.intent in (
            "roadmap_followup",
            "competency_slot_fill",
            "subject_career",
            "competency_relation",
        ):
            return False
        if route.intent == "pathfinding" and "career" in route.missing_slots:
            return True
        if route.intent == "course_rec" and "competency" in route.missing_slots:
            return True
        return False

    @staticmethod
    def _missing_slots_prompt(route: IntentRouteResult) -> str:
        missing = route.missing_slots
        if "career" in missing and "competency" in missing:
            return (
                "Bạn muốn tư vấn về nghề nghiệp IT nào, hay kỹ năng cụ thể nào bạn muốn học?\n"
                "Ví dụ: Data Analyst, Backend Developer, Python, SQL..."
            )
        if "career" in missing:
            return (
                "Bạn muốn hướng tới nghề IT nào?\n"
                "Ví dụ: Data Analyst, Frontend Developer, DevOps Engineer..."
            )
        if "competency" in missing:
            return (
                "Bạn muốn học kỹ năng hoặc công nghệ nào?\n"
                "Ví dụ: Python, SQL, React, Docker..."
            )
        return "Bạn có thể nói rõ hơn câu hỏi của mình không?"

    def _try_subject_career_route(self, text: str) -> RouteOutcome | None:
        """C-03: nhận diện câu hỏi môn học → nghề nghiệp trước khi gọi LLM."""
        if has_relation_signal(text) and pick_anchor_competency(text):
            return None
        if not looks_like_subject_career_question(text):
            return None
        canonical = resolve_subject_alias(text)
        if not canonical:
            terms = subject_search_terms(text)
            if not terms:
                return None
            canonical = terms[0]
        from app.intent.models import IntentEntities, IntentRouteResult

        route = IntentRouteResult(
            domain="in",
            intent="subject_career",
            entities=IntentEntities(subject=canonical),
            confidence="high",
            missing_slots=[],
        )
        return RouteOutcome(route=route, reply=None, stop=False, parse_fallback=False)

    def _try_competency_relation_route(
        self,
        text: str,
        *,
        state: SessionState | None = None,
    ) -> RouteOutcome | None:
        if not settings.competency_relation_intent_enabled:
            return None

        from app.intent.models import IntentEntities, IntentRouteResult
        from app.session.followup import infer_competency_relation_followup

        follow_comp = infer_competency_relation_followup(state, text) if state else None
        if follow_comp:
            route = IntentRouteResult(
                domain="in",
                intent="competency_relation",
                entities=IntentEntities(competency=follow_comp),
                confidence="high",
                missing_slots=[],
            )
            return RouteOutcome(route=route, reply=None, stop=False, parse_fallback=False)

        if not should_route_competency_relation(text):
            return None

        competency = pick_anchor_competency(text)
        if not competency:
            return None

        route = IntentRouteResult(
            domain="in",
            intent="competency_relation",
            entities=IntentEntities(competency=competency),
            confidence="high",
            missing_slots=[],
        )
        return RouteOutcome(route=route, reply=None, stop=False, parse_fallback=False)

    def close(self) -> None:
        self._registry.close()
