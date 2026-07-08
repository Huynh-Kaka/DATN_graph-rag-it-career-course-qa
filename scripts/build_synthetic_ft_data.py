"""
Build synthetic fine-tune JSONL from Neo4j (paraphrase questions per career/competency).

Ghi vào thư mục riêng (mặc định data/ft_from_synthetic); dùng merge_ft_datasets.py để gộp.

Chạy: python scripts/build_synthetic_ft_data.py --per-career 4
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.generator.prompts import COURSE_REC_SYSTEM, PATHFINDING_SYSTEM
from app.graph.formatters import format_course_rec, format_pathfinding
from app.graph.repository import GraphRepository
from app.rag.paraphrase import (
    course_rec_questions,
    pathfinding_questions,
    user_prompt_keywords_block,
)
from ft_dataset_utils import ft_paths, split_by_entity, write_ft_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "ft_from_synthetic",
        help="Snapshot synthetic (merge vào data/ qua merge_ft_datasets.py)",
    )
    parser.add_argument("--per-career", type=int, default=4)
    args = parser.parse_args()

    graph = GraphRepository()
    pf_rows: list[dict] = []
    cr_rows: list[dict] = []

    cypher = """
    MATCH (c:Career)
    WHERE c.career_name IS NOT NULL
    RETURN DISTINCT trim(c.career_name) AS name LIMIT 80
    """
    careers: list[str] = []
    if graph._client.available:
        with graph._client.session() as session:
            careers = [
                str(r["name"])
                for r in session.run(cypher).data()
                if r.get("name")
            ]

    rng = random.Random(42)
    for career in careers:
        pf = graph.pathfinding(career)
        if not pf.found:
            continue
        questions = pathfinding_questions(career, max_questions=args.per_career)
        rng.shuffle(questions)
        for q in questions[: args.per_career]:
            snap = pf.model_dump()
            assistant = format_pathfinding(pf, None)
            kw = user_prompt_keywords_block(career=career)
            entity_key = career.lower()
            pf_rows.append(
                {
                    "entity_key": entity_key,
                    "intent": "pathfinding",
                    "messages": [
                        {"role": "system", "content": PATHFINDING_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"## Câu hỏi\n{q}\n\n"
                                f"{kw}"
                                f"## Dữ liệu Neo4j\n"
                                f"{json.dumps(snap, ensure_ascii=False, indent=2)}"
                            ),
                        },
                        {"role": "assistant", "content": assistant},
                    ],
                    "meta": {
                        "source": "synthetic",
                        "intent": "pathfinding",
                        "entity_key": entity_key,
                    },
                }
            )

    comp_cypher = """
    MATCH (comp)
    WHERE comp.item_name IS NOT NULL
    RETURN DISTINCT comp.item_name AS name LIMIT 60
    """
    competencies: list[str] = []
    if graph._client.available:
        with graph._client.session() as session:
            competencies = [
                str(r["name"]) for r in session.run(comp_cypher).data() if r.get("name")
            ]

    for skill in competencies:
        cr = graph.course_recommendation(skill)
        if not cr.found or not cr.courses:
            continue
        questions = course_rec_questions(skill, max_questions=min(3, args.per_career))
        rng.shuffle(questions)
        for q in questions[: min(3, args.per_career)]:
            snap = cr.model_dump()
            assistant = format_course_rec(cr)
            kw = user_prompt_keywords_block(competency=skill)
            entity_key = skill.lower()
            cr_rows.append(
                {
                    "entity_key": entity_key,
                    "intent": "course_rec",
                    "messages": [
                        {"role": "system", "content": COURSE_REC_SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                f"## Câu hỏi\n{q}\n\n"
                                f"{kw}"
                                f"## Dữ liệu Neo4j\n"
                                f"{json.dumps(snap, ensure_ascii=False, indent=2)}"
                            ),
                        },
                        {"role": "assistant", "content": assistant},
                    ],
                    "meta": {
                        "source": "synthetic",
                        "intent": "course_rec",
                        "entity_key": entity_key,
                    },
                }
            )

    graph.close()

    pf_train, pf_val = split_by_entity(pf_rows)
    cr_train, cr_val = split_by_entity(cr_rows)
    out = args.out_dir
    write_ft_jsonl(ft_paths(out, "pathfinding")[0], pf_train)
    write_ft_jsonl(ft_paths(out, "pathfinding")[1], pf_val)
    write_ft_jsonl(ft_paths(out, "course_rec")[0], cr_train)
    write_ft_jsonl(ft_paths(out, "course_rec")[1], cr_val)
    print(
        f"pathfinding train={len(pf_train)} val={len(pf_val)} | "
        f"course_rec train={len(cr_train)} val={len(cr_val)} -> {out}"
    )


if __name__ == "__main__":
    main()
