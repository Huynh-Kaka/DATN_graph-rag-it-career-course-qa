"""
Build D-01 V2 gold sets from retrieval_gold.jsonl (~80 hint + ~25 no-hint + gen subset).

Usage:
  python scripts/build_answer_gold_from_retrieval.py
  python scripts/build_answer_gold_from_retrieval.py --no-graph
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

RETRIEVAL_GOLD = PROJECT_ROOT / "data" / "eval" / "retrieval_gold.jsonl"
DEFAULT_HINT_OUT = PROJECT_ROOT / "data" / "eval" / "answer_gold_v2.jsonl"
DEFAULT_NO_HINT_OUT = PROJECT_ROOT / "data" / "eval" / "answer_gold_no_hint_v2.jsonl"
DEFAULT_GEN_OUT = PROJECT_ROOT / "data" / "eval" / "answer_gold_ablation_gen_v2.jsonl"
DEFAULT_META_OUT = PROJECT_ROOT / "data" / "eval" / "gold_build_meta.json"

TARGET_CAREERS = 50
TARGET_COURSES = 30
TARGET_NO_HINT = 25

GEN_PF_PRIORITY = (
    "Game Developer",
    "Security Engineer",
    "Data Scientist",
    "Product Manager",
    "DevOps Engineer",
    "MLOps Engineer",
    "Blockchain Developer",
    "Cloud Architect",
)
GEN_CR_PRIORITY = (
    "Go",
    "Rust",
    "Terraform",
    "Flutter",
    "Angular",
    "MongoDB",
    "Power BI",
)

_NO_HINT_QUERY_PATTERNS = (
    r"^muốn\b",
    r"^học\s+devops",
    r"^nghề\b",
    r"\bDS\b",
    r"\bPM\b",
    r"\bQA\b",
    r"^làm\b",
    r"^dev\s",
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    raw = str(text or "").strip().lower()
    aliases = {
        "c++": "cpp",
        "c#": "csharp",
        "f#": "fsharp",
        ".net": "dotnet",
        "node.js": "nodejs",
        "power bi": "powerbi",
    }
    if raw in aliases:
        return aliases[raw]
    normalized = raw
    for key, val in aliases.items():
        normalized = normalized.replace(key, val)
    return _SLUG_RE.sub("_", normalized).strip("_")[:24]


def _load_retrieval(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _is_vietnamese(text: str) -> bool:
    return bool(re.search(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", text, re.I))


def _pick_representative(rows: list[dict[str, Any]]) -> dict[str, Any]:
    vi = [r for r in rows if _is_vietnamese(str(r.get("query") or ""))]
    pool = vi or rows
    return min(pool, key=lambda r: len(str(r.get("query") or "")))


def _dedupe_career_cases(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_career: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("doc_type") != "career":
            continue
        gold_ids = row.get("gold_ids") or []
        if not gold_ids:
            continue
        career = str(gold_ids[0])
        by_career.setdefault(career, []).append(row)

    picked: list[dict[str, Any]] = []
    for career in sorted(by_career.keys()):
        rep = _pick_representative(by_career[career])
        picked.append(
            {
                "id": f"pf_v2_{_slug(career)}",
                "intent": "pathfinding",
                "query": str(rep["query"]),
                "career": career,
                "entity_hint": True,
                "gold_build_version": "v2",
                "gold_source": "derived_from_retrieval_v2",
            }
        )
        if len(picked) >= limit:
            break
    return picked


def _dedupe_course_cases(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_comp: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("doc_type") != "course":
            continue
        comp = str(row.get("gold_competency") or "").strip()
        if not comp:
            continue
        by_comp.setdefault(comp, []).append(row)

    picked: list[dict[str, Any]] = []
    for comp in sorted(by_comp.keys()):
        rep = _pick_representative(by_comp[comp])
        picked.append(
            {
                "id": f"cr_v2_{_slug(comp)}",
                "intent": "course_rec",
                "query": str(rep["query"]),
                "competency": comp,
                "entity_hint": True,
                "gold_build_version": "v2",
                "gold_source": "derived_from_retrieval_v2",
            }
        )
        if len(picked) >= limit:
            break
    return picked


def _is_no_hint_candidate(row: dict[str, Any]) -> bool:
    q = str(row.get("query") or "").strip().lower()
    if not q:
        return False
    return any(re.search(pat, q, re.I) for pat in _NO_HINT_QUERY_PATTERNS)


def _build_no_hint_cases(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    hint_ids: set[str] = set()
    out: list[dict[str, Any]] = []

    career_rows = [r for r in rows if r.get("doc_type") == "career" and _is_no_hint_candidate(r)]
    course_rows = [r for r in rows if r.get("doc_type") == "course" and _is_no_hint_candidate(r)]

    for pool, intent, field, prefix in (
        (career_rows, "pathfinding", "expected_career", "nh_pf"),
        (course_rows, "course_rec", "expected_competency", "nh_cr"),
    ):
        seen: set[str] = set()
        for row in pool:
            if intent == "pathfinding":
                key = str((row.get("gold_ids") or [""])[0])
                expected = key
            else:
                expected = str(row.get("gold_competency") or "")
                key = expected
            if not expected or key in seen:
                continue
            seen.add(key)
            cid = f"{prefix}_{_slug(expected)}"
            if cid in hint_ids:
                continue
            case: dict[str, Any] = {
                "id": cid,
                "intent": intent,
                "query": str(row["query"]),
                "entity_hint": False,
                field: expected,
                "gold_build_version": "v2",
                "gold_source": "derived_from_retrieval_v2",
            }
            out.append(case)
            hint_ids.add(cid)
            if len(out) >= limit:
                return out

    return out[:limit]


def _enrich_from_graph(cases: list[dict]) -> list[dict]:
    from app.graph.repository import GraphRepository

    graph = GraphRepository()
    if not graph._client.available:
        print("WARN: Neo4j unavailable — writing cases without gold labels.")
        graph.close()
        return cases

    enriched: list[dict] = []
    for item in cases:
        row = dict(item)
        intent = row.get("intent")
        if intent == "pathfinding":
            career = str(
                row.get("career")
                or row.get("expected_career")
                or ""
            )
            pf = graph.pathfinding(career)
            if pf.found:
                row["gold_skills"] = [c.name for c in pf.competencies[:20]]
            else:
                row["gold_skills"] = []
                print(f"WARN: pathfinding not found for {career}")
        elif intent == "course_rec":
            comp = str(
                row.get("competency")
                or row.get("expected_competency")
                or ""
            )
            cr = graph.course_recommendation(comp)
            if cr.found:
                row["gold_course_codes"] = [
                    str(c.course_code) for c in cr.courses if c.course_code
                ][:15]
            else:
                row["gold_course_codes"] = []
                print(f"WARN: course_rec not found for {comp}")
        enriched.append(row)

    graph.close()
    return enriched


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _select_generative_subset(full_cases: list[dict], target: int = 15) -> list[dict]:
    pf_by_career = {
        str(c.get("career")): c
        for c in full_cases
        if c.get("intent") == "pathfinding" and c.get("career")
    }
    cr_by_comp = {
        str(c.get("competency")): c
        for c in full_cases
        if c.get("intent") == "course_rec" and c.get("competency")
    }
    subset: list[dict] = []
    for career in GEN_PF_PRIORITY:
        row = pf_by_career.get(career)
        if row:
            subset.append(row)
    for comp in GEN_CR_PRIORITY:
        row = cr_by_comp.get(comp)
        if row:
            subset.append(row)
    if len(subset) < target:
        for row in full_cases:
            if row not in subset:
                subset.append(row)
            if len(subset) >= target:
                break
    return subset[:target]


def _write_gen_subset(full_cases: list[dict], out: Path) -> int:
    subset = _select_generative_subset(full_cases)
    _write_jsonl(out, subset)
    return len(subset)


def _neo4j_uri_hash() -> str | None:
    try:
        from app.core.config import settings

        uri = str(getattr(settings, "neo4j_uri", "") or "")
        if uri:
            return hashlib.sha256(uri.encode()).hexdigest()[:16]
    except Exception:
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval", type=Path, default=RETRIEVAL_GOLD)
    parser.add_argument("--hint-out", type=Path, default=DEFAULT_HINT_OUT)
    parser.add_argument("--no-hint-out", type=Path, default=DEFAULT_NO_HINT_OUT)
    parser.add_argument("--gen-out", type=Path, default=DEFAULT_GEN_OUT)
    parser.add_argument("--meta-out", type=Path, default=DEFAULT_META_OUT)
    parser.add_argument("--no-graph", action="store_true")
    args = parser.parse_args()

    rows = _load_retrieval(args.retrieval)
    hint_cases = _dedupe_career_cases(rows, TARGET_CAREERS) + _dedupe_course_cases(
        rows, TARGET_COURSES
    )
    no_hint_cases = _build_no_hint_cases(rows, TARGET_NO_HINT)

    if not args.no_graph:
        hint_cases = _enrich_from_graph(hint_cases)
        no_hint_cases = _enrich_from_graph(no_hint_cases)

    _write_jsonl(args.hint_out, hint_cases)
    _write_jsonl(args.no_hint_out, no_hint_cases)
    gen_n = _write_gen_subset(hint_cases, args.gen_out)

    careers_unique = {
        str(c.get("career"))
        for c in hint_cases
        if c.get("intent") == "pathfinding" and c.get("career")
    }

    meta = {
        "build_script": "scripts/build_answer_gold_from_retrieval.py",
        "build_version": "v2",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "retrieval_source": str(args.retrieval),
        "neo4j_uri_hash": _neo4j_uri_hash(),
        "counts": {
            "hint_total": len(hint_cases),
            "hint_pathfinding": sum(1 for c in hint_cases if c.get("intent") == "pathfinding"),
            "hint_course_rec": sum(1 for c in hint_cases if c.get("intent") == "course_rec"),
            "hint_careers_unique": len(careers_unique),
            "no_hint_total": len(no_hint_cases),
            "generative_subset": gen_n,
        },
        "outputs": {
            "hint": str(args.hint_out),
            "no_hint": str(args.no_hint_out),
            "generative": str(args.gen_out),
        },
    }
    args.meta_out.parent.mkdir(parents=True, exist_ok=True)
    args.meta_out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: hint {len(hint_cases)} -> {args.hint_out}")
    print(f"OK: no-hint {len(no_hint_cases)} -> {args.no_hint_out}")
    print(f"OK: generative subset {gen_n} -> {args.gen_out}")
    print(f"OK: meta -> {args.meta_out}")


if __name__ == "__main__":
    main()
