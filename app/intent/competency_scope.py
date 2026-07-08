"""Detect when user asks for skills in one competency group only (e.g. soft skills)."""

from __future__ import annotations

import re

from app.session.competency_types import need_rel_for_type, type_label
from app.session.followup import _strip_diacritics

_SCOPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "CT_SOFT",
        re.compile(
            r"(soft\s*skills?|softskill|ky\s*nang\s*mem|k[nỹ]\s*n[aă]ng\s*m[eề]m)",
            re.IGNORECASE,
        ),
    ),
    (
        "CT_CERT",
        re.compile(
            r"(chung\s*chi|chứng\s*chỉ|certification|\bcert\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "CT_LANG",
        re.compile(
            r"(ngon\s*ngu\s*lap\s*trinh|programming\s*language|ngôn\s*ngữ\s*lập\s*trình)",
            re.IGNORECASE,
        ),
    ),
    (
        "CT_FRAM",
        re.compile(r"(\bframework\b|khung\s*lam\s*viec|khung\s*công\s*nghệ)", re.IGNORECASE),
    ),
    (
        "CT_PLAT",
        re.compile(r"(\bplatform\b|n[eề]n\s*t[aả]ng)", re.IGNORECASE),
    ),
    (
        "CT_TOOL",
        re.compile(r"(\btool\b|cong\s*cu\b|công\s*cụ\b)", re.IGNORECASE),
    ),
    (
        "CT_KNOW",
        re.compile(
            r"(kien\s*thuc\s*chuyen\s*mon|kiến\s*thức\s*chuyên\s*môn|knowledge\b)",
            re.IGNORECASE,
        ),
    ),
]


def detect_competency_type_scope(
    message: str | None,
    *,
    competency_entity: str | None = None,
) -> str | None:
    """Return CT_* code when user scopes the question to one competency group."""
    parts = [message or "", competency_entity or ""]
    combined = _strip_diacritics(" ".join(parts))
    if not combined.strip():
        return None
    for type_code, pattern in _SCOPE_PATTERNS:
        if pattern.search(combined):
            return type_code
    return None


def need_rel_for_scope(type_code: str | None) -> str | None:
    if not type_code:
        return None
    return need_rel_for_type(type_code)


def scope_label_vi(type_code: str | None) -> str | None:
    if not type_code:
        return None
    return type_label(type_code)
