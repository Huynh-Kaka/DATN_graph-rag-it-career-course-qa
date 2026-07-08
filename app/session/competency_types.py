from __future__ import annotations

from typing import Literal

Phase = Literal["idle", "collecting", "gap_summary", "course"]

COMPETENCY_TYPE_ORDER: list[str] = [
    "CT_LANG",
    "CT_FRAM",
    "CT_PLAT",
    "CT_TOOL",
    "CT_KNOW",
    "CT_SOFT",
    "CT_CERT",
]

CT_TO_NEED_REL: dict[str, str] = {
    "CT_LANG": "NEED_LANG",
    "CT_FRAM": "NEED_FRAM",
    "CT_PLAT": "NEED_PLAT",
    "CT_TOOL": "NEED_TOOL",
    "CT_KNOW": "NEED_KNOW",
    "CT_SOFT": "NEED_SOFT",
    "CT_CERT": "NEED_CERT",
}

CT_TO_TEACH_REL: dict[str, str] = {
    "CT_LANG": "TEACH_LANG",
    "CT_FRAM": "TEACH_FRAM",
    "CT_PLAT": "TEACH_PLAT",
    "CT_TOOL": "TEACH_TOOL",
    "CT_KNOW": "TEACH_KNOW",
    "CT_SOFT": "TEACH_SOFT",
    "CT_CERT": "TEACH_CERT",
}

CT_TO_LABEL: dict[str, str] = {
    "CT_LANG": "Programming language",
    "CT_FRAM": "Framework",
    "CT_PLAT": "Platform",
    "CT_TOOL": "Tool",
    "CT_KNOW": "Knowledge",
    "CT_SOFT": "Soft skill",
    "CT_CERT": "Certification",
}

TYPE_ORDER_INDEX: dict[str, int] = {
    code: idx for idx, code in enumerate(COMPETENCY_TYPE_ORDER)
}


def need_rel_for_type(type_code: str) -> str | None:
    return CT_TO_NEED_REL.get(type_code)


def teach_rel_for_type(type_code: str) -> str | None:
    return CT_TO_TEACH_REL.get(type_code)


def type_label(type_code: str) -> str:
    return CT_TO_LABEL.get(type_code, type_code)
