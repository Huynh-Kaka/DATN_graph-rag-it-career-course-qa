from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from app.core.config import settings
from app.db.engine import database_enabled
from app.db.repository import ChatSessionRepository
from app.session.memory_store import MemorySessionStore
from app.session.store import SessionState


class SessionRepository(Protocol):
    async def get_or_create(self, session_id: str | None) -> SessionState: ...
    async def save(self, state: SessionState) -> None: ...
    async def append_message(
        self,
        state: SessionState,
        role: str,
        content: str,
        *,
        route_meta: dict[str, Any] | None = None,
    ) -> int | None: ...
    async def list_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]: ...
    async def session_created_at(self, session_id: str) -> datetime | None: ...
    async def list_sessions(
        self,
        *,
        limit: int = 20,
        created_after: datetime | None = None,
    ) -> list[dict[str, Any]]: ...


def create_session_repository() -> SessionRepository:
    if database_enabled():
        return ChatSessionRepository()
    return MemorySessionStore()
