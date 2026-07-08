"""Phần A: chuẩn hóa lỗi LLM — không lộ raw exception cho người dùng."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.graph.models import CompetencyItem, PathfindingResult
from app.generator.response_generator import ResponseGenerator
from app.intent.templates import GENERATOR_OVERLOAD_MESSAGE
from app.services.generator_backend import generate_reply
from app.session.store import SessionState


class _Gemini503Error(Exception):
    """Mô phỏng lỗi 503 từ google.genai SDK như log thực tế."""

    def __str__(self) -> str:
        return (
            "503 UNAVAILABLE. {'error': {'code': 503, "
            "'message': 'This model is currently experiencing high demand...', "
            "'status': 'UNAVAILABLE'}}"
        )


def test_generate_reply_normalizes_503_without_raw_dict():
    gemini = MagicMock()
    gemini.available = True
    gemini.generate.side_effect = _Gemini503Error()
    local = MagicMock()
    local.available = False

    text, backend, is_error = generate_reply(
        intent="pathfinding",
        system_prompt="sys",
        user_prompt="user",
        gemini=gemini,
        local=local,
    )

    assert is_error is True
    assert text == GENERATOR_OVERLOAD_MESSAGE
    assert backend == "gemini_error"
    assert "UNAVAILABLE" not in text
    assert "503" not in text
    assert "{'error'" not in text


def test_pathfinding_uses_static_formatter_when_graph_context_available():
    gemini = MagicMock()
    gemini.available = True
    gemini.generate.side_effect = _Gemini503Error()
    local = MagicMock()
    local.available = False

    gen = ResponseGenerator(llm=gemini, local_llm=local)
    pf = PathfindingResult(
        found=True,
        career_name="Backend Developer",
        career_code="BE",
        competencies=[
            CompetencyItem(name="Python", kind="ProgrammingLanguage", code="L_PY"),
            CompetencyItem(name="SQL", kind="Knowledge", code="K_SQL"),
        ],
    )
    state = SessionState(session_id="s-test")

    with patch("app.generator.response_generator.settings") as mock_settings:
        mock_settings.generator_confidence_threshold = 0.45
        reply = gen.pathfinding(
            user_message="Làm backend cần gì?",
            result=pf,
            state=state,
            route_confidence="high",
        )

    assert gen.last_is_error is False
    assert gen.last_generator_backend == "formatter_fallback"
    assert "UNAVAILABLE" not in reply
    assert "503" not in reply
    assert "Backend Developer" in reply or "Python" in reply


def test_slot_fill_returns_error_message_when_no_graph_fallback(monkeypatch):
    monkeypatch.setenv("GENERATOR_BACKEND", "gemini")
    from app.core import config

    config.settings = config.Settings()

    gemini = MagicMock()
    gemini.available = True
    gemini.generate.side_effect = _Gemini503Error()
    local = MagicMock()
    local.available = False

    gen = ResponseGenerator(llm=gemini, local_llm=local)
    from app.intent.models import IntentEntities, IntentRouteResult

    route = IntentRouteResult(
        domain="in",
        intent="slot_fill",
        entities=IntentEntities(),
        confidence="high",
    )
    state = SessionState(session_id="s-slot")
    fallback = "Bạn muốn hỏi về nghề IT nào?"

    reply = gen.slot_fill(
        user_message="hello",
        route=route,
        state=state,
        fallback=fallback,
    )

    assert reply == fallback
    assert gen.last_generator_backend == "formatter_fallback"


def test_chat_service_returns_is_error_on_router_llm_failure():
    import asyncio

    from app.intent.models import RouteOutcome, IntentRouteResult, IntentEntities
    from app.services.chat_service import ChatService

    class _FailingRouter:
        def route(self, message, *, user_prompt=None, state=None):
            return RouteOutcome(
                route=IntentRouteResult(
                    domain="in",
                    intent="slot_fill",
                    entities=IntentEntities(),
                    confidence="high",
                ),
                reply=GENERATOR_OVERLOAD_MESSAGE,
                stop=True,
                is_error=True,
            )

    class _StubSessions:
        async def get_or_create(self, session_id):
            from app.session.store import SessionState

            return SessionState(session_id=session_id or "s1")

        async def append_message(self, state, role, content, *, route_meta=None):
            return 1

        async def save(self, state):
            pass

    svc = ChatService(sessions=_StubSessions(), router=_FailingRouter())  # type: ignore[arg-type]
    result = asyncio.run(svc.handle_message(message="test", session_id="s1"))

    assert result["is_error"] is True
    assert result["reply"] == GENERATOR_OVERLOAD_MESSAGE
    assert "UNAVAILABLE" not in result["reply"]
