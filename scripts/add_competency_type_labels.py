"""
Add secondary Neo4j labels to :CompetencyType nodes from their type_name property.

Keeps :CompetencyType. Uses APOC (apoc.create.addLabels) when available; otherwise
runs fixed MATCH ... SET n:Label statements.

Environment (same as scripts/ingest.py):
  NEO4J_URI (default bolt://localhost:7687)
  NEO4J_USER (default neo4j)
  NEO4J_PASSWORD (default neo4j_password)

Verification (run in Browser or after script):
  MATCH (n:CompetencyType)
  RETURN n.type_name AS type_name, labels(n) AS labels
  ORDER BY type_name;

Graph visualization query:
  MATCH (n:CompetencyType) RETURN n;

Browser colors: paste the Graph Style Sheet (GraSS) via :style or Settings.

Neo4j Browser applies only ONE color rule per node when several labels match:
the rule that appears FIRST (closest to the top) in the GraSS file wins.
So: put Knowledge/Tool/... blocks BEFORE any node.CompetencyType or node.*
that sets `color`, or remove color from those — otherwise every node stays one color.

--- Neo4j Browser: Cypher to visualize all CompetencyType nodes ---
MATCH (n:CompetencyType)
RETURN n;

--- Neo4j Browser: full GraSS (màu tách bạch từng loại) ---
Import file: design/neo4j_browser_palette.grass (kéo thả vào Browser sau :style).

Inline fallback (keep ABOVE any node.* / CompetencyType color rules):
node.Knowledge { color: #FF6B00; }
node.Tool { color: #2563EB; }
node.Softskill { color: #16A34A; }
node.Platform { color: #B45309; }
node.Framework { color: #0D9488; }
node.Certification { color: #9333EA; }
node.ProgrammingLanguage { color: #0891B2; }
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError, Neo4jError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

# Whitelist: type_name property -> second label (same spelling as in the graph).
TYPE_NAME_TO_LABEL: dict[str, str] = {
    "Knowledge": "Knowledge",
    "Tool": "Tool",
    "Softskill": "Softskill",
    "Platform": "Platform",
    "Framework": "Framework",
    "Certification": "Certification",
    "ProgrammingLanguage": "ProgrammingLanguage",
}


def _apoc_add_labels_available(session) -> bool:
    """Return True if apoc.create.addLabels is registered."""
    queries = (
        "SHOW PROCEDURES YIELD name WHERE name = 'apoc.create.addLabels' RETURN name LIMIT 1",
        "CALL dbms.procedures() YIELD name WHERE name = 'apoc.create.addLabels' RETURN name LIMIT 1",
    )
    for cypher in queries:
        try:
            r = session.run(cypher)
            if r.single() is not None:
                return True
        except Neo4jError:
            continue
    return False


def _apply_with_apoc(tx, rows: list[dict[str, str]]) -> int:
    q = """
    UNWIND $rows AS row
    MATCH (n:CompetencyType {type_name: row.type_name})
    CALL apoc.create.addLabels(n, [row.label]) YIELD node
    RETURN count(node) AS updated
    """
    rec = tx.run(q, rows=rows).single()
    return int(rec["updated"]) if rec else 0


def _apply_with_plain_cypher(tx, mapping: dict[str, str]) -> int:
    total = 0
    for type_name, label in mapping.items():
        # Label must be a literal in Cypher (not a parameter).
        q = f"""
        MATCH (n:CompetencyType {{type_name: $type_name}})
        SET n:`{label}`
        RETURN count(n) AS updated
        """
        rec = tx.run(q, type_name=type_name).single()
        if rec:
            total += int(rec["updated"])
    return total


def _verify(tx) -> list[dict[str, object]]:
    q = """
    MATCH (n:CompetencyType)
    RETURN n.type_name AS type_name, labels(n) AS labels
    ORDER BY type_name
    """
    return [dict(r) for r in tx.run(q)]


def main() -> int:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")

    rows = [
        {"type_name": k, "label": v} for k, v in TYPE_NAME_TO_LABEL.items()
    ]

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            use_apoc = _apoc_add_labels_available(session)
            if use_apoc:
                print("Using APOC: apoc.create.addLabels")
                try:
                    updated = session.execute_write(_apply_with_apoc, rows)
                except ClientError as e:
                    if "ProcedureNotFound" not in str(e) and "not found" not in str(
                        e
                    ).lower():
                        raise
                    print("APOC call failed; falling back to plain Cypher.")
                    updated = session.execute_write(
                        _apply_with_plain_cypher, TYPE_NAME_TO_LABEL
                    )
            else:
                print("APOC not detected; using plain Cypher SET ... :Label")
                updated = session.execute_write(
                    _apply_with_plain_cypher, TYPE_NAME_TO_LABEL
                )

            print(f"Nodes touched (add-label operations): {updated}")

            report = session.execute_read(_verify)
            print("\nVerification — type_name vs labels(n):")
            for row in report:
                print(f"  {row['type_name']!r} -> {row['labels']}")

            missing = [
                r["type_name"]
                for r in report
                if r["type_name"] not in TYPE_NAME_TO_LABEL
            ]
            if missing:
                print("\nWarning: CompetencyType nodes with unexpected type_name:", missing)

            for type_name, label in TYPE_NAME_TO_LABEL.items():
                bad = [
                    r
                    for r in report
                    if r["type_name"] == type_name and label not in r["labels"]
                ]
                if bad:
                    print(
                        f"\nWarning: expected label {label!r} missing for type_name={type_name!r}"
                    )
                    return 1

        print("\nDone. All listed type_name values have their second label.")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
