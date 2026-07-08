from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.intent.router import IntentRouterService
from app.session.context import apply_route_to_state, build_router_user_message
from app.session.repository import create_session_repository

router = APIRouter(prefix="/api", tags=["intent"])
_router = IntentRouterService()
_sessions = create_session_repository()


class RouteRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


@router.post("/route")
async def route_intent(payload: RouteRequest):
    state = await _sessions.get_or_create(payload.session_id)

    text = (payload.message or "").strip()
    router_prompt = build_router_user_message(state, text)
    outcome = _router.route(text, user_prompt=router_prompt)
    apply_route_to_state(state, outcome.route)
    await _sessions.save(state)

    route = outcome.route.model_dump()
    return {
        "session_id": state.session_id,
        "route": route,
        "reply": outcome.reply,
        "stop": outcome.stop,
        "parse_fallback": outcome.parse_fallback,
        "career_normalized": outcome.career_normalized,
        "session": state.to_public_dict(),
    }
