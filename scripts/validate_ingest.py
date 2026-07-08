"""
Validate competency_relation Excel rows against competency sheets and relation_types.yaml.

Chạy: python scripts/validate_ingest.py [--xlsx-path ...]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.relation_registry import get_relation_registry
from scripts.ingest import COMPETENCY_SHEETS, load_relation_supplement, merge_relation_rows, read_sheet_rows

DEFAULT_XLSX = PROJECT_ROOT / "data" / "bộ dữ liệu.xlsx"


def _load_competency_codes(xlsx_path: Path) -> dict[str, str]:
    """item_code -> type_code from competency sheets."""
    codes: dict[str, str] = {}
    for sheet_name, _label in COMPETENCY_SHEETS:
        for row in read_sheet_rows(xlsx_path, sheet_name):
            ic = str(row.get("item_code") or "").strip()
            tc = str(row.get("type_code") or "").strip()
            if ic:
                codes[ic] = tc
    return codes


def _detect_requires_cycles(rows: list[dict]) -> list[str]:
    """Warn on REQUIRES cycles among softskills."""
    graph: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if str(row.get("relation_type") or "").strip().upper() != "REQUIRES":
            continue
        src = str(row.get("from_item_code") or "").strip()
        dst = str(row.get("to_item_code") or "").strip()
        if src and dst:
            graph[src].append(dst)

    warnings: list[str] = []
    visited: set[str] = set()
    stack: set[str] = set()

    def dfs(node: str) -> None:
        if node in stack:
            warnings.append(f"REQUIRES cycle detected involving {node}")
            return
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        for nxt in graph.get(node, []):
            dfs(nxt)
        stack.remove(node)

    for node in graph:
        dfs(node)
    return warnings


REL_TYPES = [
    "BUILT_ON",
    "VALIDATES",
    "SUPPORTS",
    "REQUIRES",
    "REQUIRES_KNOWLEDGE",
    "PREFERS_LANG",
]

SPOT_CHECK_PROBES = [
    ("F_REACT", "BUILT_ON", "L_JS"),
    ("C_CKA", "VALIDATES", "P_K8S"),
    ("S_LEAD", "REQUIRES", "S_COMM"),
    ("F_AGILE", "REQUIRES_KNOWLEDGE", "K_SDLC"),
]


def spot_check_neo4j() -> tuple[list[str], list[str]]:
    """Probe 5 expected edges + 1 negative in live Neo4j."""
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    from app.graph.neo4j_client import Neo4jClient

    errors: list[str] = []
    warnings: list[str] = []
    client = Neo4jClient()
    if not client.available:
        errors.append("Neo4j unavailable for spot-check")
        client.close()
        return errors, warnings

    cypher_edge = """
    MATCH (a {item_code: $from_code})-[r]->(b {item_code: $to_code})
    WHERE type(r) = $rel_type
    RETURN count(r) AS n
    """
    cypher_outgoing = """
    MATCH (a {item_code: $code})-[r]->()
    WHERE type(r) IN $rel_types
    RETURN count(r) AS n
    """
    try:
        with client.session() as session:
            for from_code, rel_type, to_code in SPOT_CHECK_PROBES:
                row = session.run(
                    cypher_edge,
                    from_code=from_code,
                    to_code=to_code,
                    rel_type=rel_type,
                ).single()
                if not row or int(row.get("n") or 0) < 1:
                    errors.append(
                        f"spot-check missing ({from_code})-[:{rel_type}]->({to_code})"
                    )
            ansible = session.run(
                cypher_outgoing, code="T_ANSIBLE", rel_types=REL_TYPES
            ).single()
            if ansible and int(ansible.get("n") or 0) > 0:
                errors.append("spot-check T_ANSIBLE should have 0 outgoing relation edges")
    except Exception as exc:
        errors.append(f"spot-check Neo4j query failed: {exc}")
    finally:
        client.close()
    return errors, warnings


def validate_xlsx(xlsx_path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    registry = get_relation_registry()
    competency_codes = _load_competency_codes(xlsx_path)
    rel_rows = merge_relation_rows(read_sheet_rows(xlsx_path, "competency_relation"))

    for i, row in enumerate(rel_rows, start=2):
        row_errors = registry.validate_excel_row(row)
        for e in row_errors:
            errors.append(f"row {i}: {e}")

        from_ic = str(row.get("from_item_code") or "").strip()
        to_ic = str(row.get("to_item_code") or "").strip()
        if from_ic and from_ic not in competency_codes:
            errors.append(f"row {i}: dangling from_item_code {from_ic}")
        if to_ic and to_ic not in competency_codes:
            errors.append(f"row {i}: dangling to_item_code {to_ic}")

    warnings.extend(_detect_requires_cycles(rel_rows))
    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Excel before/after ingest")
    parser.add_argument("--xlsx-path", type=Path, default=DEFAULT_XLSX)
    parser.add_argument(
        "--spot-check-neo4j",
        action="store_true",
        help="Probe expected relation edges in live Neo4j (run after ingest)",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not args.spot_check_neo4j:
        if not args.xlsx_path.is_file():
            print(f"ERROR: missing {args.xlsx_path}")
            sys.exit(1)
        errors, warnings = validate_xlsx(args.xlsx_path)
        for w in warnings:
            print(f"WARN: {w}")
        if errors:
            for e in errors:
                print(f"ERROR: {e}")
            sys.exit(1)
        print(f"OK: validate_ingest passed ({args.xlsx_path})")
        return

    errors, warnings = spot_check_neo4j()
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)
    print("OK: Neo4j spot-check passed (5 probes + 1 negative)")


if __name__ == "__main__":
    main()
