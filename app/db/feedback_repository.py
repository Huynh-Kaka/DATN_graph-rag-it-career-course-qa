from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.engine import session_scope
from app.db.enums import ReviewStatus
from app.db.models import ChatMessageModel, MessageFeedbackModel


class FeedbackRepository:
    async def save_feedback(
        self,
        *,
        message_id: int,
        rating: int,
        comment: str | None = None,
    ) -> dict[str, Any]:
        if rating not in (-1, 1):
            raise ValueError("rating must be -1 or 1")

        async with session_scope() as db:
            msg = await db.get(ChatMessageModel, message_id)
            if msg is None:
                raise LookupError(f"message {message_id} not found")
            if msg.role != "assistant":
                raise ValueError("feedback only allowed on assistant messages")

            stmt = (
                insert(MessageFeedbackModel)
                .values(
                    message_id=message_id,
                    rating=rating,
                    comment=(comment or "").strip() or None,
                    review_status=ReviewStatus.pending,
                )
                .on_conflict_do_update(
                    index_elements=[MessageFeedbackModel.message_id],
                    set_={
                        "rating": rating,
                        "comment": (comment or "").strip() or None,
                        "review_status": ReviewStatus.pending,
                    },
                )
                .returning(MessageFeedbackModel)
            )
            row = (await db.execute(stmt)).scalar_one()
            return _feedback_to_dict(row)

    async def update_review_status(
        self,
        *,
        feedback_id: int,
        review_status: ReviewStatus,
        reviewer: str | None = None,
    ) -> dict[str, Any]:
        async with session_scope() as db:
            row = await db.get(MessageFeedbackModel, feedback_id)
            if row is None:
                raise LookupError(f"feedback {feedback_id} not found")
            row.review_status = review_status
            if reviewer:
                row.reviewer = reviewer.strip()
            await db.flush()
            return _feedback_to_dict(row)

    async def list_pending_review(self, *, limit: int = 50) -> list[dict[str, Any]]:
        async with session_scope() as db:
            stmt = (
                select(MessageFeedbackModel)
                .where(MessageFeedbackModel.review_status == ReviewStatus.pending)
                .order_by(MessageFeedbackModel.created_at.desc())
                .limit(limit)
            )
            rows = (await db.execute(stmt)).scalars().all()
            return [_feedback_to_dict(r) for r in rows]

    async def get_feedback_for_message(self, message_id: int) -> dict[str, Any] | None:
        async with session_scope() as db:
            stmt = select(MessageFeedbackModel).where(
                MessageFeedbackModel.message_id == message_id
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _feedback_to_dict(row) if row else None

    async def list_approved_messages(
        self, *, limit: int = 500
    ) -> list[dict[str, Any]]:
        async with session_scope() as db:
            stmt = (
                select(ChatMessageModel, MessageFeedbackModel)
                .join(
                    MessageFeedbackModel,
                    MessageFeedbackModel.message_id == ChatMessageModel.id,
                )
                .where(MessageFeedbackModel.review_status == ReviewStatus.approved)
                .order_by(ChatMessageModel.id.desc())
                .limit(limit)
            )
            rows = (await db.execute(stmt)).all()
            out: list[dict[str, Any]] = []
            for msg, fb in rows:
                out.append(
                    {
                        "message_id": msg.id,
                        "session_id": str(msg.session_id),
                        "content": msg.content,
                        "intent": msg.intent,
                        "route": msg.route,
                        "rating": fb.rating,
                    }
                )
            return out


def _feedback_to_dict(row: MessageFeedbackModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "message_id": row.message_id,
        "rating": row.rating,
        "comment": row.comment,
        "review_status": row.review_status.value
        if hasattr(row.review_status, "value")
        else str(row.review_status),
        "reviewer": row.reviewer,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
