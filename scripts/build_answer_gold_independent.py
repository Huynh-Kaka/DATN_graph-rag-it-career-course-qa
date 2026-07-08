"""
Build D-01 independent gold from Excel source (no GraphRepository).

Usage:
  python scripts/build_answer_gold_independent.py
  python scripts/build_answer_gold_independent.py --target 45 --xlsx data/bộ dữ liệu.xlsx
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from scripts.ingest import (  # noqa: E402
    CAREER_COMPETENCY_DENYLIST,
    COMPETENCY_SHEETS,
    DEFAULT_XLSX_PATH,
    read_sheet_rows,
)

DEFAULT_OUT = PROJECT_ROOT / "data" / "eval" / "answer_gold_independent.jsonl"
DEFAULT_META_OUT = PROJECT_ROOT / "data" / "eval" / "gold_independent_meta.json"
NO_HINT_SEED = PROJECT_ROOT / "data" / "eval" / "answer_gold_no_hint_v2.jsonl"
HINT_SEED = PROJECT_ROOT / "data" / "eval" / "answer_gold_v2.jsonl"

GOLD_SOURCE = "excel_derived"
GOLD_SOURCE_LEGACY = "human_verified_from_excel"
PROVENANCE_NOTE = (
    "Gold labels derived from the same Excel workbook used for Neo4j ingest; "
    "independent of GraphRepository at evaluation runtime."
)
MAX_SKILLS = 20
MAX_COURSES = 15

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("_", str(text or "").strip().lower())[:32]


def _priority_value(row: dict[str, Any]) -> float:
    raw = row.get("priority_group")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 999.0


def _coverage_value(row: dict[str, Any]) -> float:
    raw = row.get("coverage_level")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def build_item_name_index(sheet_cache: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    """item_code -> item_name from competency sheets."""
    index: dict[str, str] = {}
    for sheet_name, _label in COMPETENCY_SHEETS:
        for row in sheet_cache.get(sheet_name, []):
            code = str(row.get("item_code") or "").strip()
            name = str(row.get("item_name") or "").strip()
            if code and name:
                index[code] = name
    return index


def build_career_name_index(career_rows: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(r.get("career_code") or "").strip(): str(r.get("career_name") or "").strip()
        for r in career_rows
        if r.get("career_code") and r.get("career_name")
    }


def pathfinding_gold_from_excel(
    career_name: str,
    *,
    career_rows: list[dict[str, Any]],
    career_map_rows: list[dict[str, Any]],
    item_names: dict[str, str],
) -> list[str]:
    code_by_name = {
        str(r.get("career_name") or "").strip(): str(r.get("career_code") or "").strip()
        for r in career_rows
        if r.get("career_name") and r.get("career_code")
    }
    career_code = code_by_name.get(career_name.strip())
    if not career_code:
        return []

    rows = [
        r
        for r in career_map_rows
        if str(r.get("career_code") or "").strip() == career_code
        and (str(r.get("career_code") or "").strip(), str(r.get("item_code") or "").strip())
        not in CAREER_COMPETENCY_DENYLIST
        and r.get("type_code")
    ]
    rows.sort(key=_priority_value)
    skills: list[str] = []
    seen: set[str] = set()
    for row in rows:
        ic = str(row.get("item_code") or "").strip()
        name = item_names.get(ic) or ic
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            skills.append(name)
        if len(skills) >= MAX_SKILLS:
            break
    return skills


def course_rec_gold_from_excel(
    competency_name: str,
    *,
    course_map_rows: list[dict[str, Any]],
    item_names: dict[str, str],
) -> list[str]:
    name_to_code = {v: k for k, v in item_names.items()}
    item_code = name_to_code.get(competency_name.strip())
    if not item_code:
        for code, name in item_names.items():
            if name.lower() == competency_name.strip().lower():
                item_code = code
                break
    if not item_code:
        return []

    rows = [
        r
        for r in course_map_rows
        if str(r.get("item_code") or "").strip() == item_code
        and str(r.get("relation_type") or "TEACH").strip().upper() == "TEACH"
    ]
    rows.sort(key=_coverage_value, reverse=True)
    codes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        cc = str(row.get("course_code") or "").strip()
        if cc and cc not in seen:
            seen.add(cc)
            codes.append(cc)
        if len(codes) >= MAX_COURSES:
            break
    return codes


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _seed_case_templates(target: int) -> list[dict[str, Any]]:
    """Prefer no-hint queries, then hint v2, until target templates."""
    templates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(row: dict[str, Any]) -> None:
        key = f"{row.get('intent')}::{row.get('query')}"
        if key in seen:
            return
        seen.add(key)
        templates.append(row)

    for row in _load_jsonl(NO_HINT_SEED):
        add(row)
    for row in _load_jsonl(HINT_SEED):
        add(row)
    return templates[:target]


def build_independent_cases(
    xlsx_path: Path,
    *,
    target: int = 45,
) -> list[dict[str, Any]]:
    sheet_cache: dict[str, list[dict[str, Any]]] = {
        "career": read_sheet_rows(xlsx_path, "career"),
        "career_competency_map": read_sheet_rows(xlsx_path, "career_competency_map"),
        "course_competency_map": read_sheet_rows(xlsx_path, "course_competency_map"),
    }
    for sheet_name, _ in COMPETENCY_SHEETS:
        sheet_cache[sheet_name] = read_sheet_rows(xlsx_path, sheet_name)

    item_names = build_item_name_index(sheet_cache)
    career_rows = sheet_cache["career"]
    career_map = sheet_cache["career_competency_map"]
    course_map = sheet_cache["course_competency_map"]

    out: list[dict[str, Any]] = []
    for seed in _seed_case_templates(target):
        intent = str(seed.get("intent") or "pathfinding")
        query = str(seed.get("query") or "").strip()
        entity_hint = seed.get("entity_hint", True)
        if isinstance(entity_hint, str):
            entity_hint = entity_hint.lower() not in ("false", "0", "no")

        row: dict[str, Any] = {
            "id": f"ind_{_slug(seed.get('id') or query)}",
            "intent": intent,
            "query": query,
            "entity_hint": entity_hint,
            "gold_source": GOLD_SOURCE,
            "gold_build_version": "independent_v1",
        }

        if intent == "pathfinding":
            career = str(
                seed.get("career")
                or seed.get("expected_career")
                or (seed.get("expected_careers") or [""])[0]
                or ""
            ).strip()
            if entity_hint:
                row["career"] = career
            else:
                row["expected_career"] = career
            skills = pathfinding_gold_from_excel(
                career,
                career_rows=career_rows,
                career_map_rows=career_map,
                item_names=item_names,
            )
            if not skills:
                continue
            row["gold_skills"] = skills

        elif intent == "course_rec":
            comp = str(
                seed.get("competency")
                or seed.get("expected_competency")
                or seed.get("gold_competency")
                or ""
            ).strip()
            if entity_hint:
                row["competency"] = comp
            else:
                row["expected_competency"] = comp
            codes = course_rec_gold_from_excel(
                comp,
                course_map_rows=course_map,
                item_names=item_names,
            )
            if not codes:
                continue
            row["gold_course_codes"] = codes
        else:
            continue

        out.append(row)
        if len(out) >= target:
            break

    return out


def tag_rows_with_gold_source(rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy.setdefault("gold_source", source)
        tagged.append(copy)
    return tagged


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build independent answer gold from Excel")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--meta-out", type=Path, default=DEFAULT_META_OUT)
    parser.add_argument("--target", type=int, default=45)
    args = parser.parse_args()

    if not args.xlsx.is_file():
        print(f"ERROR: Excel not found: {args.xlsx}")
        sys.exit(1)

    cases = build_independent_cases(args.xlsx, target=args.target)
    if len(cases) < 40:
        print(f"WARN: only built {len(cases)} cases (target {args.target})")

    _write_jsonl(args.out, cases)

    meta = {
        "build_script": "scripts/build_answer_gold_independent.py",
        "gold_source": GOLD_SOURCE,
        "gold_source_legacy": GOLD_SOURCE_LEGACY,
        "provenance_note": PROVENANCE_NOTE,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "xlsx_source": str(args.xlsx),
        "count": len(cases),
        "output": str(args.out),
    }
    args.meta_out.parent.mkdir(parents=True, exist_ok=True)
    args.meta_out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: wrote {len(cases)} independent cases -> {args.out}")
    print(f"OK: meta -> {args.meta_out}")


if __name__ == "__main__":
    main()
