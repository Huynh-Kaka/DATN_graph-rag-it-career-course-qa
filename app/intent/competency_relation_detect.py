"""Detect competency relation questions (prerequisite, cert, supports)."""

from __future__ import annotations

import os
import re
import unicodedata

from app.rag.aliases import resolve_all_career_aliases, resolve_all_competency_aliases

_REL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(can|phai|nen)\s+(hoc|biet|co)\s+.*(truoc|tien quyet)",
        re.IGNORECASE,
    ),
    re.compile(r"(chung chi|cert)\s+.*(nao|gi)", re.IGNORECASE),
    re.compile(r"(lien quan|chung nhan|validates?).*(platform|nen tang)", re.IGNORECASE),
    re.compile(r"(ho tro|supports?).*(ngon ngu|language)", re.IGNORECASE),
    re.compile(r"dung\s+(ngon ngu|language)\s+gi", re.IGNORECASE),
    re.compile(r"built\s*on|xay\s+tren", re.IGNORECASE),
    re.compile(r"prerequisite|tien quyet|hoc truoc|can biet gi", re.IGNORECASE),
    re.compile(r"validate|chung nhan", re.IGNORECASE),
    re.compile(r"(ngon ngu|language)\s+nao", re.IGNORECASE),
]

_COMPARISON_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"truoc\s+hay", re.IGNORECASE),
    re.compile(r"hay\s+.*\s+truoc", re.IGNORECASE),
    re.compile(r"so\s+voi", re.IGNORECASE),
    re.compile(r"cai nao truoc", re.IGNORECASE),
]


def _strip_diacritics(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in norm if not unicodedata.combining(c)).replace("đ", "d").replace("Đ", "D")


def _probe(text: str) -> str:
    return _strip_diacritics((text or "").lower())


def has_relation_signal(text: str) -> bool:
    if not text or len(text.strip()) < 6:
        return False
    return any(p.search(_probe(text)) for p in _REL_PATTERNS)


def looks_like_competency_relation_question(text: str) -> bool:
    return has_relation_signal(text)


def comparison_pattern(text: str) -> bool:
    probe = _probe(text)
    return any(p.search(probe) for p in _COMPARISON_PATTERNS)


def _route_threshold() -> float:
    try:
        return float(os.getenv("COMPETENCY_RELATION_ROUTE_THRESHOLD", "3.0") or "3.0")
    except ValueError:
        return 3.0


def score_course_rec_affinity(text: str) -> float:
    """Lexical score suggesting course_rec over competency_relation."""
    if not text:
        return 0.0
    probe = _probe(text)
    score = 0.0
    if re.search(r"khoa\s*hoc|\bkhoa\b|\bcourse\b", probe):
        score += 2.0
    if re.search(r"goi\s*y|de\s*xuat|recommend", probe):
        score += 1.5
    if re.search(r"hoc\s+.+\s+(tu\s+dau|cho\s+nguoi\s+moi|beginner)", probe):
        score += 1.5
    if re.search(r"hoc\s+\w+.*\s+cho\b", probe):
        score += 1.5
    if re.search(r"tai\s*lieu|\bresource\b|lo\s*trinh\s+hoc", probe):
        score += 1.0
    if has_relation_signal(text):
        score -= 2.0
    if comparison_pattern(text):
        score -= 2.0
    return score


def score_competency_relation_route(text: str) -> float:
    """
    Score routing to competency_relation (higher = more likely).
    Hybrid career + multi-competency + relation signal scores highest.
    """
    if not text or len(text.strip()) < 4:
        return 0.0

    score = 0.0
    relation = has_relation_signal(text)
    comps = resolve_all_competency_aliases(text)
    careers = resolve_all_career_aliases(text)

    if relation:
        score += 3.0
    if len(comps) >= 2 and (relation or comparison_pattern(text)):
        score += 2.0
    if len(comps) >= 1 and comparison_pattern(text):
        score += 2.0
    if len(comps) >= 1:
        score += 1.0
    if careers and score < 3.0:
        score -= 1.0
    if careers and len(comps) >= 2 and relation:
        score += 1.0

    cr_affinity = score_course_rec_affinity(text)
    if cr_affinity >= 2.0 and score < 4.0:
        return min(score, _route_threshold() - 0.5)

    return score


def should_route_competency_relation(text: str) -> bool:
    rel_score = score_competency_relation_route(text)
    if rel_score < _route_threshold():
        return False
    cr_affinity = score_course_rec_affinity(text)
    if cr_affinity >= 2.0 and not has_relation_signal(text):
        return False
    return True


def pick_anchor_competency(text: str) -> str | None:
    """Primary competency for relation query (first resolved alias)."""
    comps = resolve_all_competency_aliases(text)
    if comps:
        return comps[0]
    return None
