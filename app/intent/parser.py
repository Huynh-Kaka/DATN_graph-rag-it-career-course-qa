from __future__ import annotations

import json
import re
from typing import Any

from app.intent.models import IntentEntities, IntentRouteResult

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = _JSON_FENCE_RE.sub("", cleaned).strip()
    return cleaned


def parse_route_json(raw: str) -> IntentRouteResult:
    cleaned = strip_json_fence(raw)
    data: dict[str, Any] = json.loads(cleaned)

    entities_raw = data.get("entities") or {}
    entities = IntentEntities(
        career=_nullable_str(entities_raw.get("career")),
        competency=_nullable_str(entities_raw.get("competency")),
        subject=_nullable_str(entities_raw.get("subject")),
    )

    missing = data.get("missing_slots") or []
    if not isinstance(missing, list):
        missing = []

    return IntentRouteResult(
        domain=_require_literal(data.get("domain"), ("in", "out"), default="in"),
        intent=_require_literal(
            data.get("intent"),
            (
                "slot_fill",
                "pathfinding",
                "course_rec",
                "roadmap_followup",
                "competency_slot_fill",
                "subject_career",
            ),
            default="slot_fill",
        ),
        entities=entities,
        confidence=_require_literal(data.get("confidence"), ("high", "low"), default="high"),
        missing_slots=[str(s) for s in missing if s],
    )


def fallback_route() -> IntentRouteResult:
    return IntentRouteResult(
        domain="in",
        intent="slot_fill",
        entities=IntentEntities(),
        confidence="high",
        missing_slots=["career", "competency"],
    )


def _nullable_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_literal(value: Any, allowed: tuple[str, ...], *, default: str) -> str:
    if value in allowed:
        return str(value)
    return default
