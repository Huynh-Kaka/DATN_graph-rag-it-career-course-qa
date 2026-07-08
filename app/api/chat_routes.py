from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.engine import database_enabled
from app.db.feedback_repository import FeedbackRepository
from app.intent.templates import GENERATOR_UNKNOWN_ERROR_MESSAGE
from app.response.api_shape import shape_chat_response
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

_chat: ChatService | None = None
_feedback: FeedbackRepository | None = None


def _chat_service() -> ChatService:
    global _chat
    if _chat is None:
        _chat = ChatService()
    return _chat


def _feedback_repo() -> FeedbackRepository:
    global _feedback
    if _feedback is None:
        _feedback = FeedbackRepository()
    return _feedback


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = None
    is_retry: bool = False


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    action: str | None = None
    form_url: str | None = None
    route: dict | None = None
    session: dict | None = None
    message_id: int | None = None
    structured: dict | None = None
    evidence: dict | None = None
    generator_backend: str | None = None
    llm_router: str | None = None
    is_error: bool = False


class FeedbackRequest(BaseModel):
    rating: int = Field(..., description="+1 thumbs up, -1 thumbs down")
    comment: str | None = Field(None, max_length=2000)


@router.get("/chat/greeting")
async def chat_greeting():
    return {"reply": ChatService.greeting()}


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    return await _chat_service().get_session(session_id)


@router.get("/session/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    return await _chat_service().get_history(session_id, limit=limit)


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
):
    return await _chat_service().list_sessions(limit=limit)


@router.post("/chat")
async def chat(body: ChatRequest) -> ChatResponse:
    try:
        data = await _chat_service().handle_message(
            message=body.message,
            session_id=body.session_id,
            is_retry=body.is_retry,
        )
        return ChatResponse(**shape_chat_response(data))
    except Exception:
        logger.exception("Unhandled chat error")
        return ChatResponse(
            session_id=body.session_id or "",
            reply=GENERATOR_UNKNOWN_ERROR_MESSAGE,
            is_error=True,
        )


@router.post("/chat/messages/{message_id}/feedback")
async def submit_message_feedback(message_id: int, body: FeedbackRequest):
    if not database_enabled():
        raise HTTPException(
            status_code=503,
            detail="Feedback requires DATABASE_URL (PostgreSQL).",
        )
    if body.rating not in (-1, 1):
        raise HTTPException(status_code=400, detail="rating must be -1 or 1")
    try:
        row = await _feedback_repo().save_feedback(
            message_id=message_id,
            rating=body.rating,
            comment=body.comment,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="message not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row
