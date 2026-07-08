from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_ALIASES_PATH = _DATA_DIR / "domain_aliases.json"
_ALIASES_UPGRADED_PATH = _DATA_DIR / "domain_aliases_upgraded.json"


def _aliases_file() -> Path:
    override = (os.getenv("DOMAIN_ALIASES_PATH") or "").strip()
    if override:
        p = Path(override)
        if p.is_file():
            return p
    if _ALIASES_PATH.is_file():
        return _ALIASES_PATH
    if _ALIASES_UPGRADED_PATH.is_file():
        return _ALIASES_UPGRADED_PATH
    return _ALIASES_PATH


@lru_cache(maxsize=1)
def load_aliases() -> dict[str, Any]:
    path = _aliases_file()
    if not path.is_file():
        return {
            "careers": {},
            "competencies": {},
            "soft_skills": {},
            "subjects": {},
            "abbrev_to_career": {},
        }
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _boundary_pattern(alias: str) -> re.Pattern[str] | None:
    alias = (alias or "").strip()
    if len(alias) < 2:
        return None
    if re.match(r"^[\w#+.]+$", alias, re.UNICODE):
        return re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
    return re.compile(re.escape(alias), re.IGNORECASE)


@lru_cache(maxsize=1)
def _career_alias_entries() -> list[tuple[str, str, re.Pattern[str] | None]]:
    """(alias_norm, canonical, boundary_pattern) sorted longest alias first."""
    data = load_aliases()
    entries: list[tuple[str, str]] = []
    for canonical, block in (data.get("careers") or {}).items():
        entries.append((_norm(canonical), canonical))
        for key in ("vi", "abbrev"):
            for alias in block.get(key) or []:
                entries.append((_norm(alias), canonical))
    for abbrev, value in (data.get("abbrev_to_career") or {}).items():
        canonical = resolve_abbrev_career(abbrev, context="")
        if canonical:
            entries.append((_norm(abbrev), canonical))
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, re.Pattern[str] | None]] = []
    for alias_norm, canonical in sorted(entries, key=lambda x: -len(x[0])):
        if not alias_norm or (alias_norm, canonical) in seen:
            continue
        seen.add((alias_norm, canonical))
        out.append((alias_norm, canonical, _boundary_pattern(alias_norm)))
    return out


@lru_cache(maxsize=1)
def _competency_alias_entries() -> list[tuple[str, str, re.Pattern[str] | None]]:
    data = load_aliases()
    entries: list[tuple[str, str]] = []
    for canonical, block in (data.get("competencies") or {}).items():
        entries.append((_norm(canonical), canonical))
        for key in ("vi", "abbrev"):
            for alias in block.get(key) or []:
                entries.append((_norm(alias), canonical))
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, re.Pattern[str] | None]] = []
    for alias_norm, canonical in sorted(entries, key=lambda x: -len(x[0])):
        if not alias_norm or len(alias_norm) < 2 or (alias_norm, canonical) in seen:
            continue
        seen.add((alias_norm, canonical))
        out.append((alias_norm, canonical, _boundary_pattern(alias_norm)))
    return out


@lru_cache(maxsize=1)
def _soft_skill_alias_entries() -> list[tuple[str, str, re.Pattern[str] | None]]:
    data = load_aliases()
    entries: list[tuple[str, str]] = []
    for canonical, block in (data.get("soft_skills") or {}).items():
        entries.append((_norm(canonical), canonical))
        for key in ("vi", "abbrev"):
            for alias in block.get(key) or []:
                entries.append((_norm(alias), canonical))
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, re.Pattern[str] | None]] = []
    for alias_norm, canonical in sorted(entries, key=lambda x: -len(x[0])):
        if not alias_norm or len(alias_norm) < 3 or (alias_norm, canonical) in seen:
            continue
        seen.add((alias_norm, canonical))
        out.append((alias_norm, canonical, _boundary_pattern(alias_norm)))
    return out


@lru_cache(maxsize=1)
def _subject_alias_entries() -> list[tuple[str, str, re.Pattern[str] | None]]:
    data = load_aliases()
    entries: list[tuple[str, str]] = []
    for canonical, block in (data.get("subjects") or {}).items():
        entries.append((_norm(canonical), canonical))
        for key in ("vi", "abbrev"):
            for alias in block.get(key) or []:
                entries.append((_norm(alias), canonical))
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str, re.Pattern[str] | None]] = []
    for alias_norm, canonical in sorted(entries, key=lambda x: -len(x[0])):
        if not alias_norm or len(alias_norm) < 3 or (alias_norm, canonical) in seen:
            continue
        seen.add((alias_norm, canonical))
        out.append((alias_norm, canonical, _boundary_pattern(alias_norm)))
    return out


def resolve_abbrev_career(abbrev: str, *, context: str = "") -> str | None:
    """Resolve career abbrev; ambiguous entries use default or context hint."""
    data = load_aliases()
    entry = (data.get("abbrev_to_career") or {}).get((abbrev or "").strip())
    if entry is None:
        return None
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        return None
    candidates = list(entry.get("candidates") or [])
    default = entry.get("default")
    if not candidates:
        return str(default) if default else None
    ctx = _norm(context)
    if ctx:
        for cand in candidates:
            block = (data.get("careers") or {}).get(cand) or {}
            keys = [_norm(cand)] + [_norm(a) for a in (block.get("vi") or [])]
            if any(k and k in ctx for k in keys):
                return cand
    return str(default) if default else candidates[0]


def resolve_career_alias(text: str | None) -> str | None:
    matches = resolve_all_career_aliases(text)
    return matches[0] if matches else None


def resolve_competency_alias(text: str | None) -> str | None:
    matches = resolve_all_competency_aliases(text)
    return matches[0] if matches else None


def resolve_soft_skill_alias(text: str | None) -> str | None:
    matches = resolve_all_soft_skill_aliases(text)
    return matches[0] if matches else None


def resolve_subject_alias(text: str | None) -> str | None:
    matches = resolve_all_subject_aliases(text)
    return matches[0] if matches else None


# C-03: gợi ý câu hỏi môn học → nghề nghiệp.
_SUBJECT_CAREER_HINTS = (
    "học môn",
    "môn học",
    "môn ",
    "sau này làm",
    "làm được nghề",
    "làm được những nghề",
    "ra nghề",
    "liên quan nghề",
    "đóng góp",
    "năng lực nào",
    "chương trình học",
    "học xong",
    "học môn này",
)


def looks_like_subject_career_question(text: str | None) -> bool:
    """True nếu câu hỏi mang tính liên kết môn học ↔ nghề nghiệp."""
    if not text:
        return False
    needle = _norm(text)
    if any(hint in needle for hint in _SUBJECT_CAREER_HINTS):
        return True
    return resolve_subject_alias(text) is not None and any(
        k in needle for k in ("nghề", "làm gì", "làm được", "career", "sau này")
    )


def subject_search_terms(text_or_canonical: str | None) -> list[str]:
    """
    C-03: Chuẩn hóa tên môn → danh sách term tìm CONTAINS trên Neo4j subject_name.
    Gồm tên canonical, tiếng Việt, viết tắt (OOP, CSDL, ...).
    """
    if not text_or_canonical:
        return []
    canonical = resolve_subject_alias(text_or_canonical) or text_or_canonical.strip()
    entry = get_subject_entry(canonical)
    raw_terms = [canonical] + entry["vi"] + entry["abbrev"]
    if text_or_canonical.strip() and text_or_canonical.strip() not in raw_terms:
        raw_terms.append(text_or_canonical.strip())
    out: list[str] = []
    seen: set[str] = set()
    for term in raw_terms:
        t = (term or "").strip()
        if not t:
            continue
        key = _norm(t)
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _scan_all_matches(
    text: str | None,
    entries: list[tuple[str, str, re.Pattern[str] | None]],
    *,
    min_len: int = 2,
) -> list[str]:
    if not text:
        return []
    needle = _norm(text)
    if not needle:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for alias_norm, canonical, pattern in entries:
        if len(alias_norm) < min_len:
            continue
        matched = False
        if alias_norm == needle:
            matched = True
        elif pattern is not None and pattern.search(text):
            matched = True
        elif len(alias_norm) >= 4 and alias_norm in needle:
            matched = True
        if matched and canonical not in seen:
            seen.add(canonical)
            found.append(canonical)
    return found


def resolve_all_career_aliases(text: str | None) -> list[str]:
    return _scan_all_matches(text, _career_alias_entries(), min_len=2)


def resolve_all_competency_aliases(text: str | None) -> list[str]:
    return _scan_all_matches(text, _competency_alias_entries(), min_len=2)


def resolve_all_soft_skill_aliases(text: str | None) -> list[str]:
    return _scan_all_matches(text, _soft_skill_alias_entries(), min_len=3)


def resolve_all_subject_aliases(text: str | None) -> list[str]:
    return _scan_all_matches(text, _subject_alias_entries(), min_len=3)


def competencies_from_subject(subject_key: str | None) -> list[str]:
    """Map canonical subject → competency names from maps_to_competencies."""
    if not subject_key:
        return []
    data = load_aliases()
    block = (data.get("subjects") or {}).get(subject_key) or {}
    comps = list(block.get("maps_to_competencies") or [])
    out: list[str] = []
    seen: set[str] = set()
    for name in comps:
        label = (name or "").strip()
        if label and label not in seen:
            seen.add(label)
            out.append(label)
    return out


def resolve_alias_any(text: str | None) -> dict[str, str]:
    """Resolve first match per kind (backward compatible)."""
    out: dict[str, str] = {}
    careers = resolve_all_career_aliases(text)
    if careers:
        out["career"] = careers[0]
    comps = resolve_all_competency_aliases(text)
    if comps:
        out["competency"] = comps[0]
    softs = resolve_all_soft_skill_aliases(text)
    if softs:
        out["soft_skill"] = softs[0]
    subjects = resolve_all_subject_aliases(text)
    if subjects:
        out["subject"] = subjects[0]
    return out


def resolve_alias_all(text: str | None) -> dict[str, list[str]]:
    """All matches per kind."""
    careers = resolve_all_career_aliases(text)
    comps = resolve_all_competency_aliases(text)
    softs = resolve_all_soft_skill_aliases(text)
    subjects = resolve_all_subject_aliases(text)
    subject_comps: list[str] = []
    for subj in subjects:
        subject_comps.extend(competencies_from_subject(subj))
    if subject_comps:
        seen: set[str] = set()
        merged = list(comps)
        for c in subject_comps:
            if c not in seen:
                seen.add(c)
                merged.append(c)
        comps = merged
    return {
        "careers": careers,
        "competencies": comps,
        "soft_skills": softs,
        "subjects": subjects,
    }


def get_career_entry(canonical: str) -> dict[str, list[str]]:
    data = load_aliases()
    block = (data.get("careers") or {}).get(canonical) or {}
    return {
        "vi": list(block.get("vi") or []),
        "abbrev": list(block.get("abbrev") or []),
    }


def get_competency_entry(canonical: str) -> dict[str, list[str]]:
    data = load_aliases()
    block = (data.get("competencies") or {}).get(canonical) or {}
    return {
        "vi": list(block.get("vi") or []),
        "abbrev": list(block.get("abbrev") or []),
    }


def get_soft_skill_entry(canonical: str) -> dict[str, list[str]]:
    data = load_aliases()
    block = (data.get("soft_skills") or {}).get(canonical) or {}
    return {
        "vi": list(block.get("vi") or []),
        "abbrev": list(block.get("abbrev") or []),
    }


def get_subject_entry(canonical: str) -> dict[str, list[str]]:
    data = load_aliases()
    block = (data.get("subjects") or {}).get(canonical) or {}
    return {
        "vi": list(block.get("vi") or []),
        "abbrev": list(block.get("abbrev") or []),
        "maps_to_competencies": list(block.get("maps_to_competencies") or []),
    }


def all_keywords_for_career(canonical: str) -> list[str]:
    entry = get_career_entry(canonical)
    keys = [canonical] + entry["vi"] + entry["abbrev"]
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        nk = _norm(k)
        if nk and nk not in seen:
            seen.add(nk)
            out.append(k)
    return out


def all_keywords_for_competency(canonical: str) -> list[str]:
    entry = get_competency_entry(canonical)
    keys = [canonical] + entry["vi"] + entry["abbrev"]
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        nk = _norm(k)
        if nk and nk not in seen:
            seen.add(nk)
            out.append(k)
    return out


def all_keywords_for_soft_skill(canonical: str) -> list[str]:
    entry = get_soft_skill_entry(canonical)
    keys = [canonical] + entry["vi"] + entry["abbrev"]
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        nk = _norm(k)
        if nk and nk not in seen:
            seen.add(nk)
            out.append(k)
    return out


def all_keywords_for_subject(canonical: str) -> list[str]:
    entry = get_subject_entry(canonical)
    keys = [canonical] + entry["vi"] + entry["abbrev"]
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        nk = _norm(k)
        if nk and nk not in seen:
            seen.add(nk)
            out.append(k)
    return out


def keywords_block(canonical: str, *, kind: str = "career") -> str:
    if kind == "competency":
        keys = all_keywords_for_competency(canonical)
    elif kind == "soft_skill":
        keys = all_keywords_for_soft_skill(canonical)
    elif kind == "subject":
        keys = all_keywords_for_subject(canonical)
    else:
        keys = all_keywords_for_career(canonical)
    if not keys:
        return ""
    return "Từ khóa tìm kiếm: " + ", ".join(keys[:20])
