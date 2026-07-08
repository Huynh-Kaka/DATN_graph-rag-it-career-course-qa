from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.engine import session_scope
from app.db.models import ChatMessageModel, ChatSessionModel
from app.db.profile_repository import load_profile_for_session
from app.session.models import ChatTurn
from app.db.profile_snapshot import ProfileSnapshot
from app.session.store import SessionState


def _parse_session_id(session_id: str | None) -> uuid.UUID | None:
    if not session_id or not str(session_id).strip():
        return None
    try:
        return uuid.UUID(str(session_id).strip())
    except ValueError:
        return None


def _coerce_known_by_type(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, val in raw.items():
        if not isinstance(key, str):
            continue
        if isinstance(val, list):
            out[key] = [str(s) for s in val if s]
    return out


def _coerce_phase(
    raw: str | None,
    *,
    index: int = 0,
    known_by_type: dict[str, list[str]] | None = None,
) -> str:
    known = known_by_type or {}
    if raw == "idle":
        return "idle"
    if raw in ("gap_summary", "course"):
        return raw
    if raw == "collecting":
        if index == 0 and not known:
            return "idle"
        return "collecting"
    return "idle"


def _orm_to_state(
    row: ChatSessionModel,
    *,
    messages: list[ChatTurn],
    profile: ProfileSnapshot | None,
) -> SessionState:
    return SessionState(
        session_id=str(row.id),
        profile_id=str(row.profile_id) if row.profile_id else None,
        profile=profile,
        career=row.career,
        competency=row.competency,
        competency_type_index=int(row.competency_type_index or 0),
        known_by_type=_coerce_known_by_type(row.known_by_type),
        phase=_coerce_phase(
            row.phase,
            index=int(row.competency_type_index or 0),
            known_by_type=_coerce_known_by_type(row.known_by_type),
        ),
        missing_slots=list(row.missing_slots or []),
        last_route=row.last_route,
        last_intent=row.last_intent,
        last_domain_out=bool(row.last_domain_out),
        pending_message=row.pending_message or "",
        messages=messages,
    )


def _state_to_orm(state: SessionState, row: ChatSessionModel) -> None:
    if state.profile_id:
        try:
            row.profile_id = uuid.UUID(state.profile_id)
        except ValueError:
            pass
    row.career = state.career
    row.competency = state.competency
    row.competency_type_index = int(state.competency_type_index)
    row.known_by_type = dict(state.known_by_type or {})
    row.phase = (
        state.phase
        if state.phase in ("idle", "collecting", "gap_summary", "course")
        else "idle"
    )
    row.last_intent = state.last_intent
    row.missing_slots = list(state.missing_slots or [])
    row.last_route = state.last_route
    row.last_domain_out = state.last_domain_out
    row.pending_message = state.pending_message


class ChatSessionRepository:
    """PostgreSQL persistence — SQLAlchemy async + asyncpg."""

    def __init__(self, *, message_limit: int = 24) -> None:
        self._message_limit = message_limit

    async def get_or_create(self, session_id: str | None) -> SessionState:
        async with session_scope() as db:
            sid = _parse_session_id(session_id)
            row: ChatSessionModel | None = None
            if sid is not None:
                row = await self._load_session(db, sid)
            if row is None:
                row = ChatSessionModel(id=sid if sid is not None else uuid.uuid4())
                db.add(row)
                await db.flush()
            messages = await self._load_messages(db, row.id)
            profile = await load_profile_for_session(db, row)
            return _orm_to_state(row, messages=messages, profile=profile)

    async def save(self, state: SessionState) -> None:
        sid = uuid.UUID(state.session_id)
        async with session_scope() as db:
            row = await self._load_session(db, sid)
            if row is None:
                row = ChatSessionModel(id=sid)
                db.add(row)
            _state_to_orm(state, row)

    async def append_message(
        self,
        state: SessionState,
        role: str,
        content: str,
        *,
        route_meta: dict[str, Any] | None = None,
    ) -> int | None:
        text = (content or "").strip()
        if not text:
            return None

        intent = domain = None
        route = None
        if route_meta:
            intent = route_meta.get("intent")
            domain = route_meta.get("domain")
            route = route_meta.get("route")

        state.append_message(role, text, max_messages=self._message_limit, intent=intent)

        sid = uuid.UUID(state.session_id)

        async with session_scope() as db:
            row = await self._load_session(db, sid)
            if row is None:
                row = ChatSessionModel(id=sid)
                db.add(row)
                _state_to_orm(state, row)
            else:
                _state_to_orm(state, row)

            msg = ChatMessageModel(
                session_id=sid,
                role=role,
                content=text,
                intent=intent,
                domain=domain,
                route=route,
            )
            db.add(msg)
            await db.flush()
            return int(msg.id)

    async def session_created_at(self, session_id: str) -> datetime | None:
        sid = _parse_session_id(session_id)
        if sid is None:
            return None
        async with session_scope() as db:
            row = await self._load_session(db, sid)
            return row.created_at if row else None

    async def list_messages(
        self, session_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        sid = _parse_session_id(session_id)
        if sid is None:
            return []
        async with session_scope() as db:
            stmt = (
                select(ChatMessageModel)
                .where(ChatMessageModel.session_id == sid)
                .order_by(ChatMessageModel.id.desc())
                .limit(limit)
            )
            rows = (await db.execute(stmt)).scalars().all()
            rows = list(reversed(rows))
            return [
                {
                    "id": r.id,
                    "role": r.role,
                    "content": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "intent": r.intent,
                    "domain": r.domain,
                    "route": r.route,
                    "is_error": r.intent == "_system_error",
                }
                for r in rows
            ]

    async def list_sessions(
        self,
        *,
        limit: int = 20,
        created_after: datetime | None = None,
    ) -> list[dict[str, Any]]:
        async with session_scope() as db:
            stmt = select(ChatSessionModel).order_by(ChatSessionModel.updated_at.desc())
            if created_after is not None:
                stmt = stmt.where(ChatSessionModel.created_at >= created_after)
            stmt = stmt.limit(limit)
            rows = (await db.execute(stmt)).scalars().all()
            out: list[dict[str, Any]] = []
            for row in rows:
                preview_stmt = (
                    select(ChatMessageModel.content)
                    .where(
                        ChatMessageModel.session_id == row.id,
                        ChatMessageModel.role == "user",
                    )
                    .order_by(ChatMessageModel.id.asc())
                    .limit(1)
                )
                preview = (await db.execute(preview_stmt)).scalar_one_or_none() or ""
                out.append(
                    {
                        "session_id": str(row.id),
                        "preview": preview,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                        "message_count": int(
                            (
                                await db.execute(
                                    select(func.count(ChatMessageModel.id)).where(
                                        ChatMessageModel.session_id == row.id
                                    )
                                )
                            ).scalar_one()
                            or 0
                        ),
                    }
                )
            return out

    async def _load_session(
        self, db: AsyncSession, sid: uuid.UUID
    ) -> ChatSessionModel | None:
        stmt = (
            select(ChatSessionModel)
            .where(ChatSessionModel.id == sid)
            .options(selectinload(ChatSessionModel.profile))
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def _load_messages(
        self, db: AsyncSession, sid: uuid.UUID
    ) -> list[ChatTurn]:
        stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == sid)
            .order_by(ChatMessageModel.id.desc())
            .limit(self._message_limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        rows = list(reversed(rows))
        return [ChatTurn(role=r.role, content=r.content) for r in rows]
