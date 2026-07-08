"""Load relation type definitions from data/relation_types.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "relation_types.yaml"

TYPE_CODE_TO_LABEL: dict[str, str] = {
    "CT_LANG": "ProgrammingLanguage",
    "CT_FRAM": "Framework",
    "CT_PLAT": "Platform",
    "CT_TOOL": "Tool",
    "CT_KNOW": "Knowledge",
    "CT_SOFT": "Softskill",
    "CT_CERT": "Certification",
}

LABEL_TO_TYPE_CODE: dict[str, str] = {v: k for k, v in TYPE_CODE_TO_LABEL.items()}


class RelationRegistry:
    def __init__(self, data: dict[str, Any]) -> None:
        self._types: dict[str, dict[str, Any]] = data.get("relation_types") or {}

    @classmethod
    def load(cls, path: Path | None = None) -> RelationRegistry:
        p = path or DEFAULT_REGISTRY_PATH
        with p.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return cls(raw)

    def known_relation_types(self) -> set[str]:
        return set(self._types.keys())

    def get_spec(self, rel_type: str) -> dict[str, Any] | None:
        return self._types.get(rel_type)

    def get_direction(self, anchor_type_code: str, rel_type: str) -> str:
        spec = self.get_spec(rel_type)
        if not spec:
            return "outgoing"
        direction = spec.get("direction_for_anchor")
        if isinstance(direction, dict):
            return str(direction.get(anchor_type_code) or "outgoing")
        return str(direction or "outgoing")

    def rel_types_for_anchor(self, anchor_type_code: str, *, intent_only: bool = False) -> list[str]:
        out: list[str] = []
        for rel_type, spec in self._types.items():
            if intent_only and spec.get("expose_in_intent") is False:
                continue
            primary = spec.get("anchor_type_primary") or []
            from_types = spec.get("from_types") or []
            to_types = spec.get("to_types") or []
            if anchor_type_code in primary:
                out.append(rel_type)
            elif anchor_type_code in from_types or anchor_type_code in to_types:
                out.append(rel_type)
        return out

    def ordering_rel_types(self) -> list[str]:
        return [
            rel_type
            for rel_type, spec in self._types.items()
            if spec.get("participates_in_ordering")
        ]

    def primary_anchor_types(self) -> list[str]:
        seen: list[str] = []
        for spec in self._types.values():
            for tc in spec.get("anchor_type_primary") or []:
                if tc not in seen:
                    seen.append(tc)
        return seen

    def validate_excel_row(self, row: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        rel_type = str(row.get("relation_type") or "").strip().upper()
        from_tc = str(row.get("from_type_code") or "").strip()
        to_tc = str(row.get("to_type_code") or "").strip()
        from_ic = str(row.get("from_item_code") or "").strip()
        to_ic = str(row.get("to_item_code") or "").strip()

        if not rel_type:
            errors.append("missing relation_type")
            return errors
        spec = self.get_spec(rel_type)
        if not spec:
            errors.append(f"unknown relation_type: {rel_type}")
            return errors
        if from_tc and from_tc not in (spec.get("from_types") or []):
            errors.append(f"{rel_type}: from_type_code {from_tc} not in registry from_types")
        if to_tc and to_tc not in (spec.get("to_types") or []):
            errors.append(f"{rel_type}: to_type_code {to_tc} not in registry to_types")
        if not from_ic:
            errors.append("missing from_item_code")
        if not to_ic:
            errors.append("missing to_item_code")
        return errors


@lru_cache(maxsize=1)
def get_relation_registry() -> RelationRegistry:
    return RelationRegistry.load()
