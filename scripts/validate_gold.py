"""
Validate answer gold JSONL before ablation runs (D-01 V2 Phase 0).

Usage:
  python scripts/validate_gold.py data/eval/answer_gold_v2.jsonl
  python scripts/validate_gold.py data/eval/answer_gold_no_hint_v2.jsonl --probe-neo4j
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALIASES = PROJECT_ROOT / "data" / "domain_aliases.json"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def _load_career_catalog(aliases_path: Path) -> set[str]:
    if not aliases_path.is_file():
        return set()
    data = json.loads(aliases_path.read_text(encoding="utf-8"))
    return {str(k).strip() for k in (data.get("careers") or {}).keys() if str(k).strip()}


def _norm_key(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def validate_gold_rows(
    rows: list[dict[str, Any]],
    *,
    career_catalog: set[str] | None = None,
    probe_neo4j: bool = False,
) -> tuple[list[str], list[str]]:
    if rows and rows[0].get("question") and not rows[0].get("query"):
        return _validate_quality_gold_rows(
            rows, career_catalog=career_catalog, probe_neo4j=probe_neo4j
        )
    return _validate_ablation_gold_rows(
        rows, career_catalog=career_catalog, probe_neo4j=probe_neo4j
    )


def _validate_quality_gold_rows(
    rows: list[dict[str, Any]],
    *,
    career_catalog: set[str] | None = None,
    probe_neo4j: bool = False,
) -> tuple[list[str], list[str]]:
    """D-03 answer_quality_gold schema (question / expected_skills)."""
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: dict[str, int] = {}

    for idx, row in enumerate(rows, start=1):
        case_id = str(row.get("id") or f"row_{idx}")
        intent = str(row.get("intent") or "pathfinding")
        question = str(row.get("question") or "").strip()
        gold_source = str(row.get("gold_source") or "").strip()

        if not question and not row.get("turns"):
            errors.append(f"{case_id}: missing question")
        if not gold_source:
            errors.append(f"{case_id}: missing gold_source field")
        if case_id in seen_ids:
            errors.append(f"{case_id}: duplicate id (row {seen_ids[case_id]})")
        else:
            seen_ids[case_id] = idx

        if intent == "pathfinding":
            careers = row.get("expected_careers") or []
            if not careers:
                errors.append(f"{case_id}: pathfinding requires expected_careers")
            elif career_catalog and careers[0] not in career_catalog:
                warnings.append(f"{case_id}: career '{careers[0]}' not in catalog")
        elif intent == "course_rec":
            if row.get("expected_courses") is None:
                errors.append(f"{case_id}: missing expected_courses")
        elif intent == "skills_gap":
            setup = row.get("session_setup") or {}
            if not setup.get("career") and not (row.get("expected_careers") or []):
                errors.append(f"{case_id}: skills_gap requires session_setup.career")
        elif intent == "competency_relation":
            pass
        elif intent in ("hybrid_career_relation", "multi_turn"):
            pass
        else:
            warnings.append(f"{case_id}: uncommon intent '{intent}'")

    if probe_neo4j:
        try:
            sys.path.insert(0, str(PROJECT_ROOT))
            from dotenv import load_dotenv

            load_dotenv(PROJECT_ROOT / ".env", override=True)
            from app.graph.repository import GraphRepository

            graph = GraphRepository()
            for row in rows:
                case_id = str(row.get("id") or "")
                for career in row.get("expected_careers") or []:
                    if not career:
                        continue
                    hits = graph.search_careers(str(career), limit=3)
                    names = [
                        str(c.get("name") or c.get("career_name") or "")
                        for c in (hits.get("careers") or [])
                        if isinstance(c, dict)
                    ]
                    if career not in names and not any(
                        career.lower() in n.lower() for n in names if n
                    ):
                        warnings.append(
                            f"{case_id}: Neo4j search_careers weak match for '{career}'"
                        )
            graph.close()
        except Exception as exc:
            warnings.append(f"Neo4j probe failed: {exc}")

    return errors, warnings


def _validate_ablation_gold_rows(
    rows: list[dict[str, Any]],
    *,
    career_catalog: set[str] | None = None,
    probe_neo4j: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    seen_ids: dict[str, int] = {}
    seen_intent_query: dict[tuple[str, str], int] = {}
    seen_pf_career: dict[tuple[str, str], int] = {}
    seen_cr_comp: dict[tuple[str, str], int] = {}
    seen_rel_comp: dict[tuple[str, str], int] = {}

    for idx, row in enumerate(rows, start=1):
        case_id = str(row.get("id") or f"row_{idx}")
        intent = str(row.get("intent") or "pathfinding")
        query = str(row.get("query") or "").strip()
        entity_hint = row.get("entity_hint", True)
        if isinstance(entity_hint, str):
            entity_hint = entity_hint.lower() not in ("false", "0", "no")

        if not query:
            errors.append(f"{case_id}: missing query")

        gold_source = str(row.get("gold_source") or "").strip()
        if not gold_source:
            errors.append(f"{case_id}: missing gold_source field")

        if case_id in seen_ids:
            errors.append(f"{case_id}: duplicate id (first at row {seen_ids[case_id]})")
        else:
            seen_ids[case_id] = idx

        iq = (intent, _norm_key(query))
        if iq[1] and iq in seen_intent_query:
            warnings.append(
                f"{case_id}: duplicate (intent, query) with row {seen_intent_query[iq]}"
            )
        elif iq[1]:
            seen_intent_query[iq] = idx

        if intent == "pathfinding":
            career = str(row.get("career") or row.get("target_career") or "").strip()
            expected = str(row.get("expected_career") or "").strip()
            gold_skills = row.get("gold_skills")

            if entity_hint:
                if not career:
                    errors.append(f"{case_id}: pathfinding hint-mode requires career")
                key = (intent, _norm_key(career))
                if career and key in seen_pf_career:
                    warnings.append(
                        f"{case_id}: duplicate pathfinding career '{career}' "
                        f"(row {seen_pf_career[key]})"
                    )
                elif career:
                    seen_pf_career[key] = idx
                if career_catalog and career and career not in career_catalog:
                    warnings.append(
                        f"{case_id}: career '{career}' not in domain_aliases catalog"
                    )
            else:
                if not expected:
                    errors.append(
                        f"{case_id}: no-hint pathfinding requires expected_career"
                    )
                if career:
                    warnings.append(
                        f"{case_id}: no-hint should not set career (eval leak); "
                        "use expected_career only"
                    )

            if gold_skills is None:
                errors.append(f"{case_id}: missing gold_skills field")
            elif isinstance(gold_skills, list) and len(gold_skills) == 0:
                errors.append(f"{case_id}: empty gold_skills []")

        elif intent == "course_rec":
            competency = str(row.get("competency") or row.get("gold_competency") or "").strip()
            expected_comp = str(row.get("expected_competency") or "").strip()
            gold_codes = row.get("gold_course_codes")

            if entity_hint:
                if not competency:
                    errors.append(f"{case_id}: course_rec hint-mode requires competency")
                key = (intent, _norm_key(competency))
                if competency and key in seen_cr_comp:
                    warnings.append(
                        f"{case_id}: duplicate course_rec competency '{competency}' "
                        f"(row {seen_cr_comp[key]})"
                    )
                elif competency:
                    seen_cr_comp[key] = idx
            else:
                if not expected_comp:
                    errors.append(
                        f"{case_id}: no-hint course_rec requires expected_competency"
                    )
                if competency:
                    warnings.append(
                        f"{case_id}: no-hint should not set competency; "
                        "use expected_competency only"
                    )

            if gold_codes is None:
                errors.append(f"{case_id}: missing gold_course_codes field")
            elif isinstance(gold_codes, list) and len(gold_codes) == 0:
                errors.append(f"{case_id}: empty gold_course_codes []")

        elif intent == "competency_relation":
            competency = str(row.get("competency") or "").strip()
            expected_comp = str(row.get("expected_competency") or "").strip()
            gold_codes = row.get("gold_related_codes")
            expect_cov = str(row.get("expect_coverage") or "").strip()

            if entity_hint:
                if not competency:
                    errors.append(f"{case_id}: competency_relation hint-mode requires competency")
                key = (intent, _norm_key(competency))
                if competency and key in seen_rel_comp:
                    warnings.append(
                        f"{case_id}: duplicate competency_relation '{competency}' "
                        f"(row {seen_rel_comp[key]})"
                    )
                elif competency:
                    seen_rel_comp[key] = idx
            else:
                if not expected_comp:
                    errors.append(
                        f"{case_id}: no-hint competency_relation requires expected_competency"
                    )

            if gold_codes is None:
                errors.append(f"{case_id}: missing gold_related_codes field")
            elif isinstance(gold_codes, list) and len(gold_codes) == 0:
                if expect_cov != "none":
                    warnings.append(
                        f"{case_id}: empty gold_related_codes without expect_coverage=none"
                    )

        else:
            errors.append(f"{case_id}: unsupported intent '{intent}'")

    if probe_neo4j:
        try:
            sys.path.insert(0, str(PROJECT_ROOT))
            from dotenv import load_dotenv

            load_dotenv(PROJECT_ROOT / ".env", override=True)
            from app.graph.repository import GraphRepository

            graph = GraphRepository()
            if not graph._client.available:
                warnings.append("Neo4j probe skipped: database unavailable")
            else:
                for row in rows:
                    case_id = str(row.get("id") or "")
                    intent = str(row.get("intent") or "")
                    if intent == "pathfinding":
                        career = str(
                            row.get("career")
                            or row.get("expected_career")
                            or ""
                        )
                        if career:
                            pf = graph.pathfinding(career)
                            if not pf.found:
                                warnings.append(
                                    f"{case_id}: Neo4j pathfinding not found for '{career}'"
                                )
                    elif intent == "course_rec":
                        comp = str(
                            row.get("competency")
                            or row.get("expected_competency")
                            or ""
                        )
                        if comp:
                            cr = graph.course_recommendation(comp)
                            if not cr.found:
                                warnings.append(
                                    f"{case_id}: Neo4j course_rec not found for '{comp}'"
                                )
                    elif intent == "competency_relation":
                        comp = str(
                            row.get("competency")
                            or row.get("expected_competency")
                            or ""
                        )
                        if comp:
                            rel = graph.competency_relations(comp)
                            expect = str(row.get("expect_coverage") or "").strip()
                            if expect == "none" and rel.coverage != "none":
                                warnings.append(
                                    f"{case_id}: expected coverage=none but got {rel.coverage}"
                                )
                            elif expect != "none" and not rel.found:
                                warnings.append(
                                    f"{case_id}: Neo4j competency_relations not found for '{comp}'"
                                )
            graph.close()
        except Exception as exc:
            warnings.append(f"Neo4j probe failed: {exc}")

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate D-01 answer gold JSONL")
    parser.add_argument("gold_file", type=Path)
    parser.add_argument(
        "--aliases",
        type=Path,
        default=DEFAULT_ALIASES,
        help="Career catalog from domain_aliases.json",
    )
    parser.add_argument(
        "--probe-neo4j",
        action="store_true",
        help="Optional dry-run graph lookups",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Treat warnings as errors",
    )
    args = parser.parse_args()

    if not args.gold_file.is_file():
        print(f"ERROR: file not found: {args.gold_file}")
        sys.exit(1)

    rows = _load_jsonl(args.gold_file)
    if not rows:
        print(f"ERROR: {args.gold_file} is empty")
        sys.exit(1)

    careers = _load_career_catalog(args.aliases)
    errors, warnings = validate_gold_rows(
        rows,
        career_catalog=careers,
        probe_neo4j=args.probe_neo4j,
    )

    print(f"Validated {len(rows)} cases in {args.gold_file}")
    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    if errors or (args.strict_warnings and warnings):
        print(f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s)")
        sys.exit(1)

    print(f"OK: {len(rows)} cases passed validation ({len(warnings)} warning(s))")


if __name__ == "__main__":
    main()
