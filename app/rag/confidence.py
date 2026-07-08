from __future__ import annotations

from typing import Any


def compute_confidence(
    *,
    found: bool,
    n_competencies: int = 0,
    parse_fallback: bool = False,
    route_confidence: str | None = None,
) -> float:
    """
    Heuristic confidence in [0, 1] for whether to trust LLM output vs static formatter.
    """
    score = 0.0
    if found:
        score += 0.45
    if n_competencies > 0:
        score += min(0.35, 0.05 * n_competencies)
    if route_confidence == "high":
        score += 0.15
    elif route_confidence == "low":
        score -= 0.1
    if parse_fallback:
        score -= 0.25
    return max(0.0, min(1.0, score))
