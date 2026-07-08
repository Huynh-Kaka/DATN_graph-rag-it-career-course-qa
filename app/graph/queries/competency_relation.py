"""Competency-to-competency relations (BUILT_ON, VALIDATES, …) — registry-driven."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.graph.competency_resolve import ResolveCandidate, resolve_competency_with_type_hint
from app.graph.models import (
    CompetencyRelationEdge,
    CompetencyRelationResult,
    CompetencyTypeCode,
    CoverageLevel,
)
from app.graph.neo4j_client import Neo4jClient
from app.graph.relation_registry import TYPE_CODE_TO_LABEL, get_relation_registry

logger = logging.getLogger(__name__)

_CYPHER_RELATIONS = """
MATCH (anchor {item_code: $anchor_code})
WHERE any(lbl IN labels(anchor) WHERE lbl IN $labels)
OPTIONAL MATCH (anchor)-[r_out]->(dst)
WHERE type(r_out) IN $rel_types
OPTIONAL MATCH (src)-[r_in]->(anchor)
WHERE type(r_in) IN $rel_types
RETURN anchor.item_code AS anchor_code,
       anchor.item_name AS anchor_name,
       anchor.type_code AS anchor_type_code,
       head([lbl IN labels(anchor) WHERE lbl IN $labels | lbl]) AS anchor_kind,
       collect(DISTINCT {
         relation_id: r_out.relation_id,
         rel_type: type(r_out),
         from_code: anchor.item_code,
         from_name: coalesce(anchor.item_name, anchor.item_code),
         to_code: dst.item_code,
         to_name: coalesce(dst.item_name, dst.item_code),
         from_type_code: anchor.type_code,
         to_type_code: dst.type_code,
         note: r_out.note
       }) AS outgoing_raw,
       collect(DISTINCT {
         relation_id: r_in.relation_id,
         rel_type: type(r_in),
         from_code: src.item_code,
         from_name: coalesce(src.item_name, src.item_code),
         to_code: anchor.item_code,
         to_name: coalesce(anchor.item_name, anchor.item_code),
         from_type_code: src.type_code,
         to_type_code: anchor.type_code,
         note: r_in.note
       }) AS incoming_raw
"""

_CYPHER_BATCH_ENRICH = """
UNWIND $codes AS code
MATCH (anchor {item_code: code})
WHERE any(lbl IN labels(anchor) WHERE lbl IN $labels)
OPTIONAL MATCH (anchor)-[r]->(dst)
WHERE type(r) IN $rel_types
RETURN code AS anchor_code,
       type(r) AS rel_type,
       dst.item_code AS to_code,
       coalesce(dst.item_name, dst.item_code) AS to_name,
       r.note AS note
"""

_CYPHER_BUILT_ON_TARGETS = """
MATCH (anchor {item_code: $anchor_code})-[r:BUILT_ON]->(dst)
RETURN dst.item_code AS code, coalesce(dst.item_name, dst.item_code) AS name, r.note AS note
ORDER BY dst.item_name
"""


def _parse_type_code(raw: Any) -> CompetencyTypeCode | None:
    if raw is None:
        return None
    text = str(raw).strip()
    try:
        return CompetencyTypeCode(text)
    except ValueError:
        return None


def _edge_from_dict(raw: dict[str, Any]) -> CompetencyRelationEdge | None:
    if not raw or not raw.get("rel_type") or not raw.get("to_code"):
        return None
    return CompetencyRelationEdge(
        relation_id=raw.get("relation_id"),
        rel_type=str(raw.get("rel_type") or ""),
        from_code=str(raw.get("from_code") or ""),
        from_name=str(raw.get("from_name") or ""),
        from_type_code=_parse_type_code(raw.get("from_type_code")),
        to_code=str(raw.get("to_code") or ""),
        to_name=str(raw.get("to_name") or ""),
        to_type_code=_parse_type_code(raw.get("to_type_code")),
        note=raw.get("note"),
    )


def _filter_edges(raw_list: list, rel_types: set[str], direction: str) -> list[CompetencyRelationEdge]:
    edges: list[CompetencyRelationEdge] = []
    for raw in raw_list or []:
        if not isinstance(raw, dict):
            continue
        rt = str(raw.get("rel_type") or "")
        if rt not in rel_types:
            continue
        edge = _edge_from_dict(raw)
        if edge:
            edges.append(edge)
    return edges


def fetch_competency_relations(
    client: Neo4jClient,
    competency: str,
    *,
    anchor_code: str | None = None,
    question_kind: str | None = None,
    rel_types: Sequence[str] | None = None,
) -> CompetencyRelationResult:
    registry = get_relation_registry()
    labels = list(TYPE_CODE_TO_LABEL.values())

    if not client.available:
        return CompetencyRelationResult(
            found=False,
            coverage="none",
            error="Neo4j unavailable",
        )

    try:
        resolved: ResolveCandidate | None = None
        candidates: list[ResolveCandidate] = []

        if anchor_code:
            resolved_list = resolve_competency_with_type_hint(client, anchor_code, limit=1)
            resolved = resolved_list[0] if resolved_list else None
        else:
            candidates = resolve_competency_with_type_hint(client, competency, limit=5)
            if not candidates:
                return CompetencyRelationResult(
                    found=False,
                    coverage="none",
                    error=f"Không tìm thấy competency «{competency}»",
                )
            if len(candidates) >= 2 and candidates[0].score - candidates[1].score < 5:
                return CompetencyRelationResult(
                    found=True,
                    coverage="partial",
                    error="ambiguous_competency",
                    resolve_candidates=[c.__dict__ for c in candidates],
                )
            resolved = candidates[0]

        assert resolved is not None
        anchor_tc = resolved.type_code
        if rel_types:
            rel_type_list = list(rel_types)
        else:
            rel_type_list = registry.rel_types_for_anchor(anchor_tc, intent_only=True)

        if not rel_type_list:
            return CompetencyRelationResult(
                found=True,
                anchor_name=resolved.item_name,
                anchor_code=resolved.item_code,
                anchor_type_code=_parse_type_code(anchor_tc),
                coverage="none",
            )

        rel_type_set = set(rel_type_list)
        with client.session() as session:
            row = session.run(
                _CYPHER_RELATIONS,
                anchor_code=resolved.item_code,
                labels=labels,
                rel_types=rel_type_list,
            ).single()

        if not row:
            return CompetencyRelationResult(
                found=True,
                anchor_name=resolved.item_name,
                anchor_code=resolved.item_code,
                anchor_type_code=_parse_type_code(anchor_tc),
                coverage="none",
            )

        outgoing = _filter_edges(row.get("outgoing_raw") or [], rel_type_set, "outgoing")
        incoming = _filter_edges(row.get("incoming_raw") or [], rel_type_set, "incoming")

        # Apply per-type direction from registry
        filtered_out: list[CompetencyRelationEdge] = []
        filtered_in: list[CompetencyRelationEdge] = []
        for edge in outgoing:
            direction = registry.get_direction(anchor_tc, edge.rel_type)
            if direction in ("outgoing", "both"):
                filtered_out.append(edge)
        for edge in incoming:
            direction = registry.get_direction(anchor_tc, edge.rel_type)
            if direction in ("incoming", "both"):
                filtered_in.append(edge)

        has_edges = bool(filtered_out or filtered_in)
        coverage: CoverageLevel = "full" if has_edges else "none"

        return CompetencyRelationResult(
            found=True,
            anchor_name=resolved.item_name,
            anchor_code=resolved.item_code,
            anchor_type_code=_parse_type_code(anchor_tc),
            outgoing=filtered_out,
            incoming=filtered_in,
            coverage=coverage,
            resolve_candidates=[c.__dict__ for c in candidates] if candidates else [],
        )
    except Exception as exc:
        logger.exception("fetch_competency_relations failed")
        return CompetencyRelationResult(found=False, coverage="none", error=str(exc))


def fetch_built_on_prerequisites(
    client: Neo4jClient,
    anchor_code: str,
) -> list[dict[str, str]]:
    if not client.available:
        return []
    try:
        with client.session() as session:
            rows = session.run(_CYPHER_BUILT_ON_TARGETS, anchor_code=anchor_code).data()
        return [
            {"code": str(r["code"]), "name": str(r["name"]), "note": r.get("note")}
            for r in rows
            if r.get("code")
        ]
    except Exception:
        logger.exception("fetch_built_on_prerequisites failed")
        return []


def batch_fetch_prerequisites(
    client: Neo4jClient,
    codes: Sequence[str],
) -> dict[str, list[dict[str, str]]]:
    """Batch enrich: anchor_code -> list of prerequisite targets."""
    registry = get_relation_registry()
    rel_types = registry.ordering_rel_types()
    labels = list(TYPE_CODE_TO_LABEL.values())
    out: dict[str, list[dict[str, str]]] = {c: [] for c in codes if c}

    if not client.available or not codes:
        return out

    try:
        with client.session() as session:
            rows = session.run(
                _CYPHER_BATCH_ENRICH,
                codes=list(codes),
                labels=labels,
                rel_types=rel_types,
            ).data()
        for row in rows:
            anchor = str(row.get("anchor_code") or "")
            to_code = row.get("to_code")
            if anchor and to_code:
                out.setdefault(anchor, []).append(
                    {
                        "code": str(to_code),
                        "name": str(row.get("to_name") or to_code),
                        "rel_type": str(row.get("rel_type") or ""),
                        "note": row.get("note"),
                    }
                )
    except Exception:
        logger.exception("batch_fetch_prerequisites failed")
    return out
