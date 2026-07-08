from __future__ import annotations

import re
from typing import Any

_COURSE_CITE_RE = re.compile(r"\[Course:\s*([^\]]+)\]", re.IGNORECASE)
_TECH_REL_TOKEN_RE = re.compile(
    r"\b(?:BUILT_ON|VALIDATES|SUPPORTS|REQUIRES(?:_KNOWLEDGE)?|PREFERS_LANG)\b",
    re.IGNORECASE,
)
_ITEM_CODE_RE = re.compile(r"\([A-Z]_[A-Z0-9_]+\)")
_REL_SECTION_RE = re.compile(
    r"(?im)^\s*(?:###?\s*)?(?:liên quan|outgoing|incoming).*$"
)


def extract_course_codes_from_snapshot(graph_snapshot: dict[str, Any] | None) -> set[str]:
    if not graph_snapshot:
        return set()
    codes: set[str] = set()
    for c in graph_snapshot.get("courses") or []:
        if isinstance(c, dict) and c.get("course_code"):
            codes.add(str(c["course_code"]).strip().upper())
    return codes


def validate_and_strip_hallucinated_citations(
    text: str,
    *,
    graph_snapshot: dict[str, Any] | None,
) -> tuple[str, bool]:
    """
    Remove [Course: CODE] citations not present in graph snapshot.
    Returns (cleaned_text, had_hallucination).
    """
    allowed = extract_course_codes_from_snapshot(graph_snapshot)
    if not allowed:
        return text, False

    had_hallucination = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal had_hallucination
        code = match.group(1).strip().upper()
        if code in allowed:
            return match.group(0)
        had_hallucination = True
        return ""

    cleaned = _COURSE_CITE_RE.sub(_replace, text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, had_hallucination


def count_course_citations(
    text: str,
    *,
    graph_snapshot: dict[str, Any] | None,
) -> dict[str, int]:
    """
    D-03 proxy metric: đếm trích dẫn [Course: CODE] hợp lệ vs tổng số.
    """
    allowed = extract_course_codes_from_snapshot(graph_snapshot)
    cites = [c.strip().upper() for c in _COURSE_CITE_RE.findall(text or "")]
    if not cites:
        return {
            "n_citations": 0,
            "n_valid_citations": 0,
            "n_invalid_citations": 0,
        }
    if not allowed:
        return {
            "n_citations": len(cites),
            "n_valid_citations": 0,
            "n_invalid_citations": len(cites),
        }
    valid = [c for c in cites if c in allowed]
    return {
        "n_citations": len(cites),
        "n_valid_citations": len(valid),
        "n_invalid_citations": len(cites) - len(valid),
    }


def sanitize_relation_reply(text: str) -> str:
    """Strip leaked graph tokens from competency_relation LLM output."""
    if not text:
        return text
    cleaned = text.replace("\\_", "_").replace("\\*", "*")
    cleaned = _REL_SECTION_RE.sub("", cleaned)
    cleaned = _TECH_REL_TOKEN_RE.sub("", cleaned)
    cleaned = _ITEM_CODE_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"  +", " ", cleaned)
    return cleaned.strip()
