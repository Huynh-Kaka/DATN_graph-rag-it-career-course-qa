from __future__ import annotations

import logging

from app.generator.prompts import (
    COMPETENCY_RELATION_SYSTEM,
    COURSE_REC_SYSTEM,
    PATHFINDING_SYSTEM,
    SLOT_FILL_SYSTEM,
    build_competency_relation_user_prompt,
    build_course_rec_user_prompt,
    build_pathfinding_user_prompt,
    build_slot_fill_user_prompt,
)
from app.generator.validator import (
    sanitize_relation_reply,
    validate_and_strip_hallucinated_citations,
)
from app.graph.formatters import (
    format_competency_relation,
    format_course_rec,
    format_pathfinding,
)
from app.graph.models import CompetencyRelationResult, CourseRecResult, PathfindingResult
from app.intent.models import IntentRouteResult
from app.rag.confidence import compute_confidence
from app.core.config import settings
from app.services.gemini_generator_client import GeminiGeneratorClient
from app.services.generator_backend import generate_reply
from app.services.local_generator_client import LocalGeneratorClient
from app.session.store import SessionState

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """Sinh câu trả lời: Local FT (pathfinding/course_rec) → Gemini → formatter tĩnh."""

    def __init__(
        self,
        llm: GeminiGeneratorClient | None = None,
        local_llm: LocalGeneratorClient | None = None,
    ) -> None:
        self._gemini = llm or GeminiGeneratorClient()
        self._local = local_llm or LocalGeneratorClient()
        self.last_generator_backend: str | None = None
        self.last_is_error: bool = False

    def _generate_text(
        self,
        *,
        intent: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        text, backend, is_error = generate_reply(
            intent=intent,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            gemini=self._gemini,
            local=self._local,
        )
        self.last_generator_backend = backend
        self.last_is_error = is_error
        return text

    def slot_fill(
        self,
        *,
        user_message: str,
        route: IntentRouteResult,
        state: SessionState,
        fallback: str,
    ) -> str:
        if not self._gemini.available:
            return fallback
        try:
            text = self._generate_text(
                intent="slot_fill",
                system_prompt=SLOT_FILL_SYSTEM,
                user_prompt=build_slot_fill_user_prompt(
                    user_message=user_message,
                    route=route,
                    state=state,
                ),
            )
            if self.last_is_error:
                self.last_generator_backend = "formatter_fallback"
                return fallback
            return text
        except Exception as exc:
            logger.warning("Generator slot_fill failed: %s", exc)
            self.last_generator_backend = "formatter_fallback"
            self.last_is_error = True
            return fallback

    def pathfinding(
        self,
        *,
        user_message: str,
        result: PathfindingResult,
        state: SessionState,
        vector_context: str = "",
        exemplars: list[str] | None = None,
        route_confidence: str | None = None,
        competency_scope_label: str | None = None,
    ) -> str:
        fallback = format_pathfinding(result, state)
        graph_data = result.model_dump()
        n_comp = len(result.competencies) + len(result.skills_missing)
        conf = compute_confidence(
            found=result.found,
            n_competencies=n_comp,
            route_confidence=route_confidence,
        )
        if not result.found or conf < settings.generator_confidence_threshold:
            self.last_generator_backend = "formatter_static"
            return fallback
        if not self._gemini.available and not self._local.available:
            self.last_generator_backend = "formatter_static"
            return fallback
        try:
            user_prompt = build_pathfinding_user_prompt(
                user_message=user_message,
                graph_data=graph_data,
                state=state,
                competency_scope_label=competency_scope_label,
            )
            user_prompt = _prepend_context(user_prompt, vector_context, exemplars)
            raw = self._generate_text(
                intent="pathfinding",
                system_prompt=PATHFINDING_SYSTEM,
                user_prompt=user_prompt,
            )
            if self.last_is_error:
                self.last_generator_backend = "formatter_fallback"
                self.last_is_error = False
                return fallback
            cleaned, _ = validate_and_strip_hallucinated_citations(
                raw, graph_snapshot=graph_data
            )
            return cleaned or fallback
        except Exception as exc:
            logger.warning("Generator pathfinding failed: %s", exc)
            self.last_generator_backend = "formatter_fallback"
            self.last_is_error = False
            return fallback

    def course_rec(
        self,
        *,
        user_message: str,
        result: CourseRecResult,
        state: SessionState,
        vector_context: str = "",
        exemplars: list[str] | None = None,
        route_confidence: str | None = None,
    ) -> str:
        fallback = format_course_rec(result)
        graph_data = result.model_dump()
        conf = compute_confidence(
            found=result.found,
            n_competencies=len(result.courses),
            route_confidence=route_confidence,
        )
        if not result.found or conf < settings.generator_confidence_threshold:
            self.last_generator_backend = "formatter_static"
            return fallback
        if not self._gemini.available and not self._local.available:
            self.last_generator_backend = "formatter_static"
            return fallback
        try:
            user_prompt = build_course_rec_user_prompt(
                user_message=user_message,
                graph_data=graph_data,
                state=state,
            )
            user_prompt = _prepend_context(user_prompt, vector_context, exemplars)
            raw = self._generate_text(
                intent="course_rec",
                system_prompt=COURSE_REC_SYSTEM,
                user_prompt=user_prompt,
            )
            if self.last_is_error:
                self.last_generator_backend = "formatter_fallback"
                self.last_is_error = False
                return fallback
            cleaned, _ = validate_and_strip_hallucinated_citations(
                raw, graph_snapshot=graph_data
            )
            return cleaned or fallback
        except Exception as exc:
            logger.warning("Generator course_rec failed: %s", exc)
            self.last_generator_backend = "formatter_fallback"
            self.last_is_error = False
            return fallback

    def competency_relation(
        self,
        *,
        user_message: str,
        result: CompetencyRelationResult,
        state: SessionState,
        vector_context: str = "",
        route_confidence: str | None = None,
    ) -> str:
        fallback = format_competency_relation(result)
        if result.coverage != "full":
            self.last_generator_backend = "formatter_static"
            return fallback
        graph_data = result.model_dump()
        if not self._gemini.available and not self._local.available:
            self.last_generator_backend = "formatter_static"
            return fallback
        try:
            user_prompt = build_competency_relation_user_prompt(
                user_message=user_message,
                graph_data=graph_data,
                state=state,
            )
            user_prompt = _prepend_context(user_prompt, vector_context, None)
            raw = self._generate_text(
                intent="competency_relation",
                system_prompt=COMPETENCY_RELATION_SYSTEM,
                user_prompt=user_prompt,
            )
            if self.last_is_error:
                self.last_generator_backend = "formatter_fallback"
                self.last_is_error = False
                return fallback
            cleaned, _ = validate_and_strip_hallucinated_citations(
                raw, graph_snapshot=graph_data
            )
            cleaned = sanitize_relation_reply(cleaned)
            return cleaned or fallback
        except Exception as exc:
            logger.warning("Generator competency_relation failed: %s", exc)
            self.last_generator_backend = "formatter_fallback"
            self.last_is_error = False
            return fallback


def _prepend_context(
    user_prompt: str,
    vector_context: str,
    exemplars: list[str] | None,
) -> str:
    parts: list[str] = []
    if exemplars:
        parts.append("## Ví dụ câu trả lời đã duyệt (tham khảo giọng văn, không copy)\n")
        for i, ex in enumerate(exemplars, 1):
            parts.append(f"### Ví dụ {i}\n{ex}\n")
    if vector_context.strip():
        parts.append(f"## Ngữ cảnh bổ sung (vector)\n{vector_context.strip()}\n\n")
    if not parts:
        return user_prompt
    return "".join(parts) + user_prompt
