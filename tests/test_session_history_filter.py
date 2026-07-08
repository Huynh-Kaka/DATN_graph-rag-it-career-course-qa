from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.services.chat_service import ChatService


def test_get_history_hidden_when_session_before_filter():
    created_after = datetime(2026, 6, 25, tzinfo=timezone.utc)
    sessions = AsyncMock()
    sessions.session_created_at.return_value = datetime(2026, 6, 20, tzinfo=timezone.utc)
    sessions.list_messages.return_value = [{"role": "user", "content": "old"}]

    svc = ChatService(sessions=sessions)
    from app.core import config

    old = config.settings.session_filter_after
    try:
        config.settings.session_filter_after = created_after
        out = asyncio.run(svc.get_history("old-session-id"))
    finally:
        config.settings.session_filter_after = old

    assert out["messages"] == []
    assert out["history_hidden"] is True
    sessions.list_messages.assert_not_called()


def test_get_history_returns_messages_when_session_after_filter():
    created_after = datetime(2026, 6, 25, tzinfo=timezone.utc)
    sessions = AsyncMock()
    sessions.session_created_at.return_value = datetime(2026, 6, 25, 12, tzinfo=timezone.utc)
    sessions.list_messages.return_value = [{"role": "user", "content": "hi"}]

    svc = ChatService(sessions=sessions)
    from app.core import config

    old = config.settings.session_filter_after
    try:
        config.settings.session_filter_after = created_after
        out = asyncio.run(svc.get_history("new-session-id"))
    finally:
        config.settings.session_filter_after = old

    assert out["messages"] == [{"role": "user", "content": "hi"}]
    assert "history_hidden" not in out


def test_resolve_session_id_returns_none_when_filter_hides_old():
    created_after = datetime(2026, 6, 25, tzinfo=timezone.utc)
    sessions = AsyncMock()
    sessions.session_created_at.return_value = datetime(2026, 6, 20, tzinfo=timezone.utc)

    svc = ChatService(sessions=sessions)
    from app.core import config

    old = config.settings.session_filter_after
    try:
        config.settings.session_filter_after = created_after
        resolved = asyncio.run(svc._resolve_session_id("old-session-id"))
    finally:
        config.settings.session_filter_after = old

    assert resolved is None
