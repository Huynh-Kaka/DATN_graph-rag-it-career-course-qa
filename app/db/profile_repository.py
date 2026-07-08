from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import session_scope
from app.db.enums import TargetRole, UserBackground, WeeklyTime
from app.db.models import AdviceResultModel, ChatSessionModel, UserProfileModel
from app.db.profile_snapshot import ProfileSnapshot


def _profile_to_snapshot(row: UserProfileModel) -> ProfileSnapshot:
    return ProfileSnapshot(
        profile_id=str(row.id),
        background=row.background.value if isinstance(row.background, UserBackground) else str(row.background),
        role=row.role.value if isinstance(row.role, TargetRole) else str(row.role),
        role_note=row.role_note,
        known_skills=list(row.known_skills or []),
        weekly_time=(
            row.weekly_time.value
            if row.weekly_time and isinstance(row.weekly_time, WeeklyTime)
            else (str(row.weekly_time) if row.weekly_time else None)
        ),
        goals=list(row.goals or []),
        initial_question=row.initial_question,
        profile_completed=bool(row.profile_completed),
    )


class ProfileRepository:
    async def create_profile(
        self,
        *,
        background: UserBackground,
        role: TargetRole,
        known_skills: list[str],
        goals: list[str],
        role_note: str | None = None,
        weekly_time: WeeklyTime | None = None,
        initial_question: str | None = None,
        profile_completed: bool = True,
    ) -> ProfileSnapshot:
        async with session_scope() as db:
            row = UserProfileModel(
                background=background,
                role=role,
                role_note=(role_note or "").strip() or None,
                known_skills=list(known_skills),
                weekly_time=weekly_time,
                goals=list(goals),
                initial_question=(initial_question or "").strip() or None,
                profile_completed=profile_completed,
            )
            db.add(row)
            await db.flush()
            return _profile_to_snapshot(row)

    async def get_profile(self, profile_id: str) -> ProfileSnapshot | None:
        pid = _parse_uuid(profile_id)
        if pid is None:
            return None
        async with session_scope() as db:
            row = await db.get(UserProfileModel, pid)
            if row is None:
                return None
            return _profile_to_snapshot(row)

    async def create_session_for_profile(
        self,
        profile_id: str,
        *,
        session_id: uuid.UUID | None = None,
        career: str | None = None,
    ) -> uuid.UUID:
        pid = _parse_uuid(profile_id)
        if pid is None:
            raise ValueError("profile_id không hợp lệ")
        async with session_scope() as db:
            profile = await db.get(UserProfileModel, pid)
            if profile is None:
                raise ValueError("Không tìm thấy profile")
            sid = session_id or uuid.uuid4()
            session_row = ChatSessionModel(
                id=sid,
                profile_id=pid,
                career=career,
            )
            db.add(session_row)
            await db.flush()
            return sid

    async def link_session_profile(
        self, session_id: str, profile_id: str, *, career: str | None = None
    ) -> None:
        sid = _parse_uuid(session_id)
        pid = _parse_uuid(profile_id)
        if sid is None or pid is None:
            raise ValueError("session_id hoặc profile_id không hợp lệ")
        async with session_scope() as db:
            session_row = await db.get(ChatSessionModel, sid)
            if session_row is None:
                raise ValueError("Không tìm thấy session")
            session_row.profile_id = pid
            if career:
                session_row.career = career

    async def save_advice(
        self,
        *,
        session_id: str,
        profile_id: str | None,
        skills_gap: dict[str, Any] | None,
        roadmap: list[Any] | None,
        recommended_courses: list[Any] | None,
        estimated_months: int | None,
        raw_response: str | None,
    ) -> str:
        sid = _parse_uuid(session_id)
        if sid is None:
            raise ValueError("session_id không hợp lệ")
        pid = _parse_uuid(profile_id) if profile_id else None
        async with session_scope() as db:
            row = AdviceResultModel(
                session_id=sid,
                profile_id=pid,
                skills_gap=skills_gap,
                roadmap=roadmap,
                recommended_courses=recommended_courses,
                estimated_months=estimated_months,
                raw_response=raw_response,
            )
            db.add(row)
            await db.flush()
            return str(row.id)

    async def get_latest_advice(self, session_id: str) -> dict[str, Any] | None:
        sid = _parse_uuid(session_id)
        if sid is None:
            return None
        async with session_scope() as db:
            stmt = (
                select(AdviceResultModel)
                .where(AdviceResultModel.session_id == sid)
                .order_by(AdviceResultModel.created_at.desc())
                .limit(1)
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return {
                "id": str(row.id),
                "session_id": str(row.session_id),
                "profile_id": str(row.profile_id) if row.profile_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "skills_gap": row.skills_gap,
                "roadmap": row.roadmap,
                "recommended_courses": row.recommended_courses,
                "estimated_months": row.estimated_months,
                "raw_response": row.raw_response,
            }


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value or not str(value).strip():
        return None
    try:
        return uuid.UUID(str(value).strip())
    except ValueError:
        return None


async def load_profile_for_session(db: AsyncSession, session_row: ChatSessionModel) -> ProfileSnapshot | None:
    if session_row.profile_id is None:
        return None
    profile = await db.get(UserProfileModel, session_row.profile_id)
    if profile is None:
        return None
    return _profile_to_snapshot(profile)
