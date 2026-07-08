from __future__ import annotations

from rapidfuzz import fuzz, process

from app.core.config import settings
from app.rag.aliases import resolve_abbrev_career, resolve_career_alias


class CareerMatcher:
    def __init__(self, career_names: list[str]) -> None:
        self._careers = career_names

    def resolve(self, raw: str | None) -> str | None:
        if not raw or not self._careers:
            return None

        needle = raw.strip()
        if not needle:
            return None

        via_alias = resolve_career_alias(needle)
        if via_alias and via_alias in self._careers:
            return via_alias

        if needle.isascii() and len(needle) <= 6:
            via_abbrev = resolve_abbrev_career(needle, context=needle)
            if via_abbrev and via_abbrev in self._careers:
                return via_abbrev

        # Khớp chính xác (không phân biệt hoa thường)
        lower_map = {c.lower(): c for c in self._careers}
        if needle.lower() in lower_map:
            return lower_map[needle.lower()]

        match = process.extractOne(
            needle,
            self._careers,
            scorer=fuzz.WRatio,
            score_cutoff=settings.router_career_fuzzy_threshold,
        )
        if match:
            return match[0]
        return None
