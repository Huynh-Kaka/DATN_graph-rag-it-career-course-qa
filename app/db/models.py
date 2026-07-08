from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import ReviewStatus, TargetRole, UserBackground, WeeklyTime

_user_background_enum = Enum(
    UserBackground,
    name="user_background",
    create_constraint=True,
    values_callable=lambda x: [e.value for e in x],
)
_target_role_enum = Enum(
    TargetRole,
    name="target_role",
    create_constraint=True,
    values_callable=lambda x: [e.value for e in x],
)
_weekly_time_enum = Enum(
    WeeklyTime,
    name="weekly_time",
    create_constraint=True,
    values_callable=lambda x: [e.value for e in x],
)
_review_status_enum = Enum(
    ReviewStatus,
    name="review_status",
    create_constraint=True,
    values_callable=lambda x: [e.value for e in x],
)


class UserProfileModel(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    background: Mapped[UserBackground] = mapped_column(_user_background_enum, nullable=False)
    role: Mapped[TargetRole] = mapped_column(_target_role_enum, nullable=False)
    role_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    known_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    weekly_time: Mapped[WeeklyTime | None] = mapped_column(_weekly_time_enum, nullable=True)
    goals: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    initial_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sessions: Mapped[list["ChatSessionModel"]] = relationship(back_populates="profile")


class ChatSessionModel(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    missing_slots: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    last_route: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_domain_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pending_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    competency: Mapped[str | None] = mapped_column(Text, nullable=True)
    career: Mapped[str | None] = mapped_column(Text, nullable=True)
    competency_type_index: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    known_by_type: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    phase: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="idle"
    )

    profile: Mapped[UserProfileModel | None] = relationship(back_populates="sessions")
    messages: Mapped[list["ChatMessageModel"]] = relationship(
        back_populates="session",
        order_by="ChatMessageModel.id",
        cascade="all, delete-orphan",
    )
    advice_results: Mapped[list["AdviceResultModel"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(8), nullable=True)
    route: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    session: Mapped[ChatSessionModel] = relationship(back_populates="messages")
    feedback: Mapped[list["MessageFeedbackModel"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class MessageFeedbackModel(Base):
    __tablename__ = "message_feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        _review_status_enum,
        nullable=False,
        default=ReviewStatus.pending,
    )
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    message: Mapped[ChatMessageModel] = relationship(back_populates="feedback")


class AdviceResultModel(Base):
    __tablename__ = "advice_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    skills_gap: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    roadmap: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    recommended_courses: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    estimated_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[ChatSessionModel] = relationship(back_populates="advice_results")
