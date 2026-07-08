"""
Measure competency_relation coverage in Excel or Neo4j.

Chạy:
  python scripts/validate_graph_coverage.py --min-relation-edges 30
  python scripts/validate_graph_coverage.py --min-coverage 0.40 --warn-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from scripts.ingest import load_relation_supplement, merge_relation_rows, read_sheet_rows

DEFAULT_XLSX = PROJECT_ROOT / "data" / "bộ dữ liệu.xlsx"


def coverage_from_excel(xlsx_path: Path) -> dict[str, float | int]:
    ccm_rows = read_sheet_rows(xlsx_path, "career_competency_map")
    career_items = {
        str(r.get("item_code") or "").strip()
        for r in ccm_rows
        if r.get("item_code")
    }

    rel_rows = merge_relation_rows(read_sheet_rows(xlsx_path, "competency_relation"))
    outgoing_sources: set[str] = set()
    for row in rel_rows:
        src = str(row.get("from_item_code") or "").strip()
        if src:
            outgoing_sources.add(src)

    touched = career_items & outgoing_sources
    ratio = len(touched) / len(career_items) if career_items else 0.0
    return {
        "relation_edges": len(rel_rows),
        "career_map_items": len(career_items),
        "items_with_outgoing": len(touched),
        "coverage_ratio": ratio,
    }


def coverage_from_neo4j() -> dict[str, float | int] | None:
    from app.graph.neo4j_client import Neo4jClient

    client = Neo4jClient()
    if not client.available:
        client.close()
        return None

    cypher_edges = """
    MATCH ()-[r]->()
    WHERE type(r) IN $rel_types
    RETURN count(r) AS edge_count
    """
    cypher_coverage = """
    MATCH (c:Career)-[need]->(comp)
    WHERE type(need) STARTS WITH 'NEED_'
    WITH collect(DISTINCT comp.item_code) AS career_items
    MATCH (src)-[r]->(dst)
    WHERE type(r) IN $rel_types AND src.item_code IS NOT NULL
    WITH career_items, collect(DISTINCT src.item_code) AS outgoing_sources
    RETURN size(career_items) AS career_map_items,
           size([x IN outgoing_sources WHERE x IN career_items]) AS items_with_outgoing,
           size(outgoing_sources) AS total_outgoing_sources
    """
    rel_types = [
        "BUILT_ON",
        "VALIDATES",
        "SUPPORTS",
        "REQUIRES",
        "REQUIRES_KNOWLEDGE",
        "PREFERS_LANG",
    ]
    try:
        with client.session() as session:
            edge_row = session.run(cypher_edges, rel_types=rel_types).single()
            cov_row = session.run(cypher_coverage, rel_types=rel_types).single()
    finally:
        client.close()

    if not cov_row:
        return None
    career_items = int(cov_row.get("career_map_items") or 0)
    with_out = int(cov_row.get("items_with_outgoing") or 0)
    ratio = with_out / career_items if career_items else 0.0
    return {
        "relation_edges": int(edge_row.get("edge_count") or 0) if edge_row else 0,
        "career_map_items": career_items,
        "items_with_outgoing": with_out,
        "coverage_ratio": ratio,
    }


def check_coverage_threshold(
    *,
    min_relation_edges: int = 0,
    min_coverage: float = 0.0,
    use_neo4j: bool = False,
    xlsx_path: Path | None = None,
    warn_only: bool = False,
) -> tuple[dict[str, float | int], bool]:
    """Return (stats, passed). Used by build_index_corpus guard."""
    stats = coverage_from_neo4j() if use_neo4j else coverage_from_excel(xlsx_path or DEFAULT_XLSX)
    if stats is None:
        stats = coverage_from_excel(xlsx_path or DEFAULT_XLSX)

    passed = True
    if stats["relation_edges"] < min_relation_edges:
        msg = f"relation_edges {stats['relation_edges']} < {min_relation_edges}"
        if warn_only:
            print(f"WARN: {msg}")
        else:
            print(f"ERROR: {msg}")
            passed = False
    if stats["coverage_ratio"] < min_coverage:
        msg = f"coverage {stats['coverage_ratio']:.1%} < {min_coverage:.1%}"
        if warn_only:
            print(f"WARN: {msg}")
        else:
            print(f"ERROR: {msg}")
            passed = False
    return stats, passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate graph relation coverage")
    parser.add_argument("--xlsx-path", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--min-relation-edges", type=int, default=0)
    parser.add_argument("--min-coverage", type=float, default=0.0)
    parser.add_argument("--use-neo4j", action="store_true")
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args()

    stats = coverage_from_neo4j() if args.use_neo4j else coverage_from_excel(args.xlsx_path)
    if stats is None:
        print("WARN: Neo4j unavailable, falling back to Excel")
        stats = coverage_from_excel(args.xlsx_path)

    print(
        f"relation_edges={stats['relation_edges']} "
        f"career_map_items={stats['career_map_items']} "
        f"items_with_outgoing={stats['items_with_outgoing']} "
        f"coverage={stats['coverage_ratio']:.1%}"
    )

    failed = False
    if stats["relation_edges"] < args.min_relation_edges:
        msg = f"relation_edges {stats['relation_edges']} < {args.min_relation_edges}"
        if args.warn_only:
            print(f"WARN: {msg}")
        else:
            print(f"ERROR: {msg}")
            failed = True
    if stats["coverage_ratio"] < args.min_coverage:
        msg = f"coverage {stats['coverage_ratio']:.1%} < {args.min_coverage:.1%}"
        if args.warn_only:
            print(f"WARN: {msg}")
        else:
            print(f"ERROR: {msg}")
            failed = True

    if failed:
        sys.exit(1)
    print("OK: coverage check passed")


if __name__ == "__main__":
    main()
