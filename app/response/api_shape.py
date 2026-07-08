"""Chuẩn hóa payload API chat trước khi validate ChatResponse."""

from __future__ import annotations

from typing import Any


def coerce_evidence(value: Any) -> dict | None:
    """ChatResponse.evidence must be dict | None (never list or other types)."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return {}


def shape_chat_response(data: dict[str, Any]) -> dict[str, Any]:
    """Apply response-level coercions shared by all chat intents."""
    out = dict(data)
    if "evidence" in out:
        out["evidence"] = coerce_evidence(out["evidence"])
    structured = out.get("structured")
    if structured is not None and not isinstance(structured, dict):
        out["structured"] = None
    return out
