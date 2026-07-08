"""Phần C: đánh dấu message lỗi khi lưu repository."""

from __future__ import annotations

import asyncio

from app.intent.templates import GENERATOR_OVERLOAD_MESSAGE, SYSTEM_ERROR_INTENT
from app.services.chat_service import ChatService
from app.session.store import SessionState


class _CapturingSessions:
    def __init__(self) -> None:
        self.last_route_meta: dict | None = None
        self.state = SessionState(session_id="s-err")

    async def get_or_create(self, session_id):
        return self.state

    async def append_message(self, state, role, content, *, route_meta=None):
        if role == "assistant" and route_meta:
            self.last_route_meta = route_meta
        return 42

    async def save(self, state):
        pass


class _ErrorRouter:
    def route(self, message, *, user_prompt=None, state=None):
        from app.intent.models import IntentEntities, IntentRouteResult, RouteOutcome

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


def test_error_message_saved_with_system_error_intent():
    sessions = _CapturingSessions()
    svc = ChatService(sessions=sessions, router=_ErrorRouter())  # type: ignore[arg-type]

    result = asyncio.run(
        svc.handle_message(message="Lộ trình backend?", session_id="s-err")
    )

    assert result["is_error"] is True
    assert sessions.last_route_meta is not None
    assert sessions.last_route_meta.get("intent") == SYSTEM_ERROR_INTENT


def test_retry_skips_duplicate_user_message():
    sessions = _CapturingSessions()
    sessions.state.messages.append(
        __import__("app.session.models", fromlist=["ChatTurn"]).ChatTurn(
            role="user", content="Lộ trình backend?"
        )
    )
    user_count_before = sum(1 for m in sessions.state.messages if m.role == "user")

    class _OkRouter:
        def route(self, message, *, user_prompt=None, state=None):
            from app.intent.models import IntentEntities, IntentRouteResult, RouteOutcome

            return RouteOutcome(
                route=IntentRouteResult(
                    domain="in",
                    intent="slot_fill",
                    entities=IntentEntities(),
                    confidence="high",
                ),
                reply="Xin chào",
                stop=True,
            )

    svc = ChatService(sessions=sessions, router=_OkRouter())  # type: ignore[arg-type]
    asyncio.run(
        svc.handle_message(
            message="Lộ trình backend?",
            session_id="s-err",
            is_retry=True,
        )
    )

    user_count_after = sum(1 for m in sessions.state.messages if m.role == "user")
    assert user_count_after == user_count_before
