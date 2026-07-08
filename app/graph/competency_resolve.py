"""Resolve free-text queries to competency nodes with type-aware disambiguation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.core.config import settings
from app.graph.models import CompetencyTypeCode
from app.graph.neo4j_client import Neo4jClient
from app.graph.relation_registry import LABEL_TO_TYPE_CODE, TYPE_CODE_TO_LABEL
from app.rag.aliases import resolve_competency_alias

_ITEM_CODE_RE = re.compile(r"^[A-Z]{1,3}_[A-Z0-9_]+$", re.IGNORECASE)

_CYPHER_LIST_ALL = """
UNWIND $labels AS lbl
CALL {
  WITH lbl
  MATCH (n)
  WHERE lbl IN labels(n) AND n.item_name IS NOT NULL
  RETURN lbl AS kind, n.item_code AS code, n.item_name AS name, n.type_code AS type_code
}
RETURN kind, code, name, type_code
ORDER BY name
"""


@dataclass
class ResolveCandidate:
    item_code: str
    item_name: str
    type_code: str
    kind: str
    score: float
    source: str  # exact | alias | fuzzy


def _type_code_from_row(row: dict) -> str:
    tc = str(row.get("type_code") or "").strip()
    if tc:
        return tc
    kind = str(row.get("kind") or "")
    return LABEL_TO_TYPE_CODE.get(kind, "")


def _load_catalog(client: Neo4jClient) -> list[dict]:
    labels = list(TYPE_CODE_TO_LABEL.values())
    with client.session() as session:
        return list(session.run(_CYPHER_LIST_ALL, labels=labels))


def resolve_competency_with_type_hint(
    client: Neo4jClient,
    query: str,
    *,
    anchor_type_hint: CompetencyTypeCode | str | None = None,
    career_context: str | None = None,
    limit: int = 5,
) -> list[ResolveCandidate]:
    if not client.available:
        return []

    needle = (query or "").strip()
    if not needle:
        return []

    catalog = _load_catalog(client)
    if not catalog:
        return []

    hint = str(anchor_type_hint.value if isinstance(anchor_type_hint, CompetencyTypeCode) else anchor_type_hint or "")

    candidates: list[ResolveCandidate] = []

    upper = needle.upper()
    if _ITEM_CODE_RE.match(upper):
        for row in catalog:
            if str(row.get("code") or "").upper() == upper:
                tc = _type_code_from_row(row)
                candidates.append(
                    ResolveCandidate(
                        item_code=str(row["code"]),
                        item_name=str(row["name"]),
                        type_code=tc,
                        kind=str(row.get("kind") or ""),
                        score=100.0,
                        source="exact",
                    )
                )
                return candidates[:limit]

    alias = resolve_competency_alias(needle)
    if alias:
        alias_lower = alias.lower()
        for row in catalog:
            name = str(row.get("name") or "")
            if name.lower() == alias_lower:
                tc = _type_code_from_row(row)
                score = 95.0
                if hint and tc == hint:
                    score += 10.0
                candidates.append(
                    ResolveCandidate(
                        item_code=str(row["code"]),
                        item_name=name,
                        type_code=tc,
                        kind=str(row.get("kind") or ""),
                        score=score,
                        source="alias",
                    )
                )

    names = [str(r["name"]) for r in catalog if r.get("name")]
    name_to_row = {str(r["name"]): r for r in catalog if r.get("name")}
    match = process.extractOne(
        needle,
        names,
        scorer=fuzz.WRatio,
        score_cutoff=max(50, settings.router_career_fuzzy_threshold - 15),
    )
    if match:
        row = name_to_row[match[0]]
        tc = _type_code_from_row(row)
        score = float(match[1])
        if hint and tc == hint:
            score += 15.0
        elif hint and tc != hint:
            score -= 5.0
        candidates.append(
            ResolveCandidate(
                item_code=str(row["code"]),
                item_name=str(row["name"]),
                type_code=tc,
                kind=str(row.get("kind") or ""),
                score=score,
                source="fuzzy",
            )
        )

    # Dedupe by code, keep best score
    best: dict[str, ResolveCandidate] = {}
    for c in candidates:
        prev = best.get(c.item_code)
        if prev is None or c.score > prev.score:
            best[c.item_code] = c

    ranked = sorted(best.values(), key=lambda x: (-x.score, x.item_name))
    return ranked[:limit]
