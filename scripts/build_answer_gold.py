"""
Sinh / cập nhật gold_skills và gold_course_codes từ Neo4j cho data/eval/answer_gold.jsonl.

Chạy:
  python scripts/build_answer_gold.py
  python scripts/build_answer_gold.py --out data/eval/answer_gold.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

DEFAULT_OUT = PROJECT_ROOT / "data" / "eval" / "answer_gold.jsonl"
DEFAULT_GEN_SUBSET_OUT = PROJECT_ROOT / "data" / "eval" / "answer_gold_ablation_gen.jsonl"

# 10 case dùng cho ablation generative (phương án B).
GENERATIVE_SUBSET_IDS: tuple[str, ...] = (
    "pf_gd_01",
    "pf_bc_01",
    "pf_sec_01",
    "pf_pm_01",
    "pf_sre_01",
    "cr_go_01",
    "cr_terraform_01",
    "cr_angular_01",
    "cr_flutter_01",
    "cr_powerbi_01",
)

# Bộ câu hỏi mẫu (25) — đa dạng ngành nghề / competency (bám retrieval_gold + ontology).
# gold_skills / gold_course_codes được điền từ Neo4j khi build.
SEED_CASES: list[dict] = [
    # pathfinding (15) — game, security, embedded, data platform, PM/BA, ...
    {"id": "pf_gd_01", "intent": "pathfinding", "query": "làm game dev thì học gì", "career": "Game Developer"},
    {"id": "pf_bc_01", "intent": "pathfinding", "query": "muốn làm blockchain", "career": "Blockchain Developer"},
    {"id": "pf_sec_01", "intent": "pathfinding", "query": "security engineer học gì", "career": "Security Engineer"},
    {"id": "pf_qa_01", "intent": "pathfinding", "query": "QA engineer cần học gì", "career": "QA Engineer"},
    {"id": "pf_pm_01", "intent": "pathfinding", "query": "product manager học gì", "career": "Product Manager"},
    {"id": "pf_emb_01", "intent": "pathfinding", "query": "embedded engineer học gì", "career": "Embedded Software Engineer"},
    {"id": "pf_arvr_01", "intent": "pathfinding", "query": "làm AR/VR developer cần gì", "career": "AR/VR Developer"},
    {"id": "pf_ae_01", "intent": "pathfinding", "query": "muốn làm analytics engineer", "career": "Analytics Engineer"},
    {"id": "pf_cv_01", "intent": "pathfinding", "query": "computer vision engineer cần gì", "career": "Computer Vision Engineer"},
    {"id": "pf_mlops_01", "intent": "pathfinding", "query": "lộ trình MLOps", "career": "MLOps Engineer"},
    {"id": "pf_sre_01", "intent": "pathfinding", "query": "SRE cần học gì", "career": "Site Reliability Engineer"},
    {"id": "pf_ca_01", "intent": "pathfinding", "query": "cloud architect là gì học gì", "career": "Cloud Architect"},
    {"id": "pf_net_01", "intent": "pathfinding", "query": "network engineer học gì", "career": "Network Engineer"},
    {"id": "pf_cyber_01", "intent": "pathfinding", "query": "cybersecurity analyst lộ trình", "career": "Cybersecurity Analyst"},
    {"id": "pf_ba_01", "intent": "pathfinding", "query": "business analyst IT học gì", "career": "Business Analyst"},
    # course_rec (10) — ngôn ngữ / framework / nền tảng khác bộ cũ
    {"id": "cr_go_01", "intent": "course_rec", "query": "khóa học Go cho backend", "competency": "Go"},
    {"id": "cr_rust_01", "intent": "course_rec", "query": "khóa Rust cho người mới", "competency": "Rust"},
    {"id": "cr_ts_01", "intent": "course_rec", "query": "học TypeScript từ đầu", "competency": "TypeScript"},
    {"id": "cr_terraform_01", "intent": "course_rec", "query": "học Terraform cơ bản", "competency": "Terraform"},
    {"id": "cr_powerbi_01", "intent": "course_rec", "query": "khóa Power BI", "competency": "Power BI"},
    {"id": "cr_angular_01", "intent": "course_rec", "query": "khóa học Angular", "competency": "Angular"},
    {"id": "cr_flutter_01", "intent": "course_rec", "query": "khóa học Flutter cho mobile", "competency": "Flutter"},
    {"id": "cr_mongo_01", "intent": "course_rec", "query": "học MongoDB cho NoSQL", "competency": "MongoDB"},
    {"id": "cr_nest_01", "intent": "course_rec", "query": "khóa NestJS Node.js", "competency": "NestJS"},
    {"id": "cr_pg_01", "intent": "course_rec", "query": "khóa PostgreSQL cơ bản", "competency": "PostgreSQL"},
]


def _enrich_from_graph(cases: list[dict]) -> list[dict]:
    from app.graph.repository import GraphRepository

    graph = GraphRepository()
    if not graph._client.available:
        print("WARN: Neo4j unavailable — writing seed cases without gold labels.")
        graph.close()
        return cases

    enriched: list[dict] = []
    for item in cases:
        row = dict(item)
        row.setdefault("gold_source", "derived_from_graph_repository")
        row.setdefault("gold_build_version", "v1_seed")
        intent = row.get("intent")
        if intent == "pathfinding":
            pf = graph.pathfinding(str(row["career"]))
            if pf.found:
                row["gold_skills"] = [c.name for c in pf.competencies[:20]]
            else:
                row["gold_skills"] = []
                print(f"WARN: pathfinding not found for {row['career']}")
        elif intent == "course_rec":
            cr = graph.course_recommendation(str(row["competency"]))
            if cr.found:
                row["gold_course_codes"] = [
                    str(c.course_code) for c in cr.courses if c.course_code
                ][:15]
            else:
                row["gold_course_codes"] = []
                print(f"WARN: course_rec not found for {row['competency']}")
        elif intent == "competency_relation":
            rel = graph.competency_relations(str(row["competency"]))
            codes: list[str] = []
            for bucket in ("outgoing", "incoming"):
                for edge in getattr(rel, bucket, []) or []:
                    codes.append(str(edge.to_code))
                    codes.append(str(edge.from_code))
            if rel.anchor_code:
                codes.append(str(rel.anchor_code))
            row["gold_related_codes"] = sorted({c for c in codes if c and c != "None"})
        enriched.append(row)

    graph.close()
    return enriched


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_gen_subset(full_cases: list[dict], out: Path) -> int:
    by_id = {str(r["id"]): r for r in full_cases if r.get("id")}
    subset: list[dict] = []
    missing: list[str] = []
    for cid in GENERATIVE_SUBSET_IDS:
        row = by_id.get(cid)
        if row:
            subset.append(row)
        else:
            missing.append(cid)
    if missing:
        print(f"WARN: generative subset missing ids: {', '.join(missing)}")
    _write_jsonl(out, subset)
    print(f"OK: wrote {len(subset)} generative subset cases to {out}")
    return len(subset)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--gen-subset-out",
        type=Path,
        default=DEFAULT_GEN_SUBSET_OUT,
        help="Also write generative ablation subset (10 ids in GENERATIVE_SUBSET_IDS)",
    )
    parser.add_argument("--no-gen-subset", action="store_true", help="Skip generative subset file")
    parser.add_argument("--no-graph", action="store_true", help="Skip Neo4j enrichment")
    args = parser.parse_args()

    cases = list(SEED_CASES)
    cases = [{**c, "gold_source": "derived_from_graph_repository", "gold_build_version": "v1_seed"} for c in cases]
    if not args.no_graph:
        cases = _enrich_from_graph(cases)

    _write_jsonl(args.out, cases)
    print(f"OK: wrote {len(cases)} cases to {args.out}")

    if not args.no_gen_subset:
        _write_gen_subset(cases, args.gen_subset_out)


if __name__ == "__main__":
    main()
