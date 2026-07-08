"""
Chuẩn hóa nhãn kỹ năng dùng chung (so khớp / dedupe), không dùng để hiển thị.
"""

from __future__ import annotations

import re
import unicodedata

_PREFIX_RE = re.compile(
    r"^(platform|tool|language|framework|library|domain)\s*:\s*",
    re.IGNORECASE,
)


def normalize_skill_label(label: str) -> str:
    if not label:
        return ""
    normalized = unicodedata.normalize("NFKD", label)
    normalized = _PREFIX_RE.sub("", normalized)
    return normalized.strip().lower()


def normalize_skill_set(labels: list[str]) -> set[str]:
    return {normalize_skill_label(lb) for lb in labels if lb}
