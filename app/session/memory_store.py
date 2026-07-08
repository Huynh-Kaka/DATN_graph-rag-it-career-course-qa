from __future__ import annotations

import uuid

from app.session.store import SessionState


class MemorySessionStore:
    """Fallback in-memory khi không có DATABASE_URL."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    async def get_or_create(self, session_id: str | None) -> SessionState:
        sid = (session_id or "").strip() or str(uuid.uuid4())
        if sid not in self._sessions:
            self._sessions[sid] = SessionState(session_id=sid)
        return self._sessions[sid]

    async def save(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state

    async def append_message(
        self,
        state: SessionState,
        role: str,
        content: str,
        *,
        route_meta: dict | None = None,
    ) -> int | None:
        intent = route_meta.get("intent") if route_meta else None
        state.append_message(role, content, intent=intent)
        self._sessions[state.session_id] = state
        return None

    async def session_created_at(self, session_id: str):
        return None

    async def list_messages(self, session_id: str, *, limit: int = 50) -> list:
        state = self._sessions.get(session_id)
        if not state:
            return []
        msgs = state.messages[-limit:]
        return [
            {
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "is_error": m.intent == "_system_error",
            }
            for m in msgs
        ]

    async def list_sessions(
        self,
        *,
        limit: int = 20,
        created_after=None,
    ) -> list[dict]:
        items: list[dict] = []
        for sid, state in self._sessions.items():
            preview = next((m.content for m in state.messages if m.role == "user"), "")
            items.append(
                {
                    "session_id": sid,
                    "preview": preview,
                    "updated_at": None,
                    "message_count": len(state.messages),
                }
            )
        items.sort(key=lambda x: x["message_count"], reverse=True)
        return items[:limit]
