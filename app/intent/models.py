from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Domain = Literal["in", "out"]
Intent = Literal[
    "slot_fill",
    "pathfinding",
    "course_rec",
    "roadmap_followup",
    "competency_slot_fill",
    "subject_career",
    "competency_relation",
]
Confidence = Literal["high", "low"]


class IntentEntities(BaseModel):
    career: str | None = None
    competency: str | None = None
    subject: str | None = None


class IntentRouteResult(BaseModel):
    domain: Domain
    intent: Intent
    entities: IntentEntities = Field(default_factory=IntentEntities)
    confidence: Confidence = "high"
    missing_slots: list[str] = Field(default_factory=list)


class RouteOutcome(BaseModel):
    """Kết quả sau Intent Router + hậu xử lý (fuzzy, template)."""

    route: IntentRouteResult
    reply: str | None = None
    stop: bool = False
    parse_fallback: bool = False
    career_normalized: bool = False
    is_error: bool = False
