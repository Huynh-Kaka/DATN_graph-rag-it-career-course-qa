"""
Skills Gap Analysis: kỹ năng cần học = yêu cầu nghề (graph) − known_skills (profile).

C-02: so khớp theo ``item_code`` (node identity Neo4j); ``apply_skills_gap_typed``
là điểm tính toán dùng chung cho roadmap + competency orchestrator.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import warnings
from typing import Iterable

from app.graph.models import CompetencyItem, PathfindingResult
from app.graph.relation_registry import get_relation_registry
from app.session.competency_types import (
    COMPETENCY_TYPE_ORDER,
    need_rel_for_type,
)
from app.session.store import SessionState
from app.utils.skill_normalize import normalize_skill_label

# Mã kỹ năng từ form → alias hiển thị (legacy string matching).
FORM_SKILL_ALIASES: dict[str, list[str]] = {
    "python": ["python"],
    "js": ["javascript", "js", "node", "nodejs", "node.js", "typescript"],
    "java": ["java", "c#", "c sharp", "csharp"],
    "sql": ["sql"],
    "html_css": ["html", "css"],
    "git": ["git"],
    "linux": ["linux"],
    "excel": ["excel", "google sheets", "sheets"],
}

# Form code → item_code graph (C-02).
FORM_SKILL_ITEM_CODES: dict[str, str | list[str]] = {
    "python": "L_PY",
    "js": "L_JS",
    "java": "L_JAVA",
    "sql": "L_SQL",
    "html_css": ["K_HTML", "K_CSS"],
    "git": "T_GIT",
    "linux": "P_LINUX",
    "excel": "T_EXCEL",
}

_ITEM_CODE_RE = re.compile(r"^[A-Z]{1,3}_[A-Z0-9_]+$", re.IGNORECASE)
_SKILL_TOKEN_RE = re.compile(r"[a-z0-9+#.]+", re.IGNORECASE)


def normalize_skill_token(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def expand_known_skill_codes(codes: list[str]) -> set[str]:
    """Legacy: chuyển mã form (python, sql…) thành tập token so khớp chuỗi."""
    tokens: set[str] = set()
    for code in codes:
        key = normalize_skill_token(code)
        if not key or key == "none":
            continue
        for alias in FORM_SKILL_ALIASES.get(key, [key]):
            tokens.add(normalize_skill_token(alias))
            for part in _SKILL_TOKEN_RE.findall(alias):
                if len(part) >= 2:
                    tokens.add(part.lower())
    return tokens


def competency_matches_known(comp_name: str, known_tokens: set[str]) -> bool:
    """Legacy string matching — chỉ dùng cho equivalence test / deprecated path."""
    if not known_tokens:
        return False
    name_norm = normalize_skill_token(comp_name)
    if name_norm in known_tokens:
        return True
    for token in _SKILL_TOKEN_RE.findall(comp_name):
        t = token.lower()
        if len(t) >= 2 and t in known_tokens:
            return True
    for known in known_tokens:
        if len(known) >= 3 and (known in name_norm or name_norm in known):
            return True
    return False


def _catalog_name_index(
    competency_catalog: Iterable[CompetencyItem] | None,
) -> dict[str, str]:
    """normalize_skill_label(name) → item_code."""
    index: dict[str, str] = {}
    for comp in competency_catalog or []:
        if not comp.code or not comp.name:
            continue
        index[normalize_skill_label(comp.name)] = comp.code
    return index


def resolve_known_item_codes(
    inputs: list[str] | None,
    *,
    competency_catalog: Iterable[CompetencyItem] | None = None,
) -> set[str]:
    """
    Chuẩn hóa profile / session / form input → tập ``item_code``.

    Thứ tự ưu tiên: mã graph trực tiếp → form map → alias + catalog name.
    """
    codes: set[str] = set()
    name_index = _catalog_name_index(competency_catalog)

    for raw in inputs or []:
        token = (raw or "").strip()
        if not token or token.lower() == "none":
            continue

        upper = token.upper()
        if _ITEM_CODE_RE.match(upper):
            codes.add(upper)
            continue

        form_key = normalize_skill_token(token)
        mapped = FORM_SKILL_ITEM_CODES.get(form_key)
        if mapped:
            if isinstance(mapped, list):
                codes.update(mapped)
            else:
                codes.add(mapped)
            continue

        alias_tokens = FORM_SKILL_ALIASES.get(form_key, [form_key])
        for alias in alias_tokens:
            norm = normalize_skill_label(alias)
            if norm in name_index:
                codes.add(name_index[norm])

        norm_label = normalize_skill_label(token)
        if norm_label in name_index:
            codes.add(name_index[norm_label])

    return codes


def competency_matches_known_code(
    comp: CompetencyItem,
    known_codes: set[str],
) -> bool:
    """So khớp chính xác theo ``item_code`` (C-02)."""
    if not known_codes or not comp.code:
        return False
    return comp.code in known_codes


def apply_skills_gap_by_code(
    result: PathfindingResult,
    known_item_codes: set[str] | None,
) -> PathfindingResult:
    """Gắn skills_known / skills_missing bằng so khớp ``item_code``."""
    known_codes = set(known_item_codes or [])
    if not result.found or not result.competencies:
        result.skills_known = []
        result.skills_missing = list(result.competencies)
        return result

    known_items: list[CompetencyItem] = []
    missing_items: list[CompetencyItem] = []
    for comp in result.competencies:
        if competency_matches_known_code(comp, known_codes):
            known_items.append(comp)
        else:
            missing_items.append(comp)

    result.skills_known = known_items
    result.skills_missing = missing_items
    return result


def apply_skills_gap_to_result(
    result: PathfindingResult,
    known_inputs: list[str] | None,
) -> PathfindingResult:
    """API dùng chung: resolve input → item_code rồi apply gap."""
    known_codes = resolve_known_item_codes(
        known_inputs,
        competency_catalog=result.competencies,
    )
    return apply_skills_gap_by_code(result, known_codes)


def apply_skills_gap(
    result: PathfindingResult,
    known_skill_codes: list[str] | None,
) -> PathfindingResult:
    """
    Deprecated — so khớp theo display name / alias string.

    Giữ lại cho equivalence test; production dùng ``apply_skills_gap_to_result``.
    """
    warnings.warn(
        "apply_skills_gap() is deprecated; use apply_skills_gap_to_result() "
        "for item_code-based matching.",
        DeprecationWarning,
        stacklevel=2,
    )
    codes = list(known_skill_codes or [])
    known_tokens = expand_known_skill_codes(codes)
    if not result.found or not result.competencies:
        result.skills_known = []
        result.skills_missing = list(result.competencies)
        return result

    known_items: list[CompetencyItem] = []
    missing_items: list[CompetencyItem] = []
    for comp in result.competencies:
        if competency_matches_known(comp.name, known_tokens):
            known_items.append(comp)
        else:
            missing_items.append(comp)

    result.skills_known = known_items
    result.skills_missing = missing_items
    return result


def _collect_known_inputs_for_type(
    state: SessionState,
    type_code: str,
    *,
    extra_known: list[str] | None = None,
) -> list[str]:
    bucket = list(state.known_by_type.get(type_code) or [])
    if not extra_known:
        return bucket
    seen = {normalize_skill_label(s) for s in bucket}
    merged = list(bucket)
    for label in extra_known:
        key = normalize_skill_label(label)
        if key and key not in seen:
            seen.add(key)
            merged.append(label)
    return merged


def apply_skills_gap_typed(
    state: SessionState,
    graph: "GraphRepositoryLike",
    *,
    career: str | None = None,
    extra_known: list[str] | None = None,
) -> dict[str, PathfindingResult]:
    """
    Pathfinding theo từng competency type + gap theo ``item_code``.

    ``extra_known``: known phẳng (profile form codes / session labels) áp cho mọi block.
    """
    target_career = (career or state.career or "").strip()
    if not target_career:
        return {}

    by_type: dict[str, PathfindingResult] = {}
    for type_code in COMPETENCY_TYPE_ORDER:
        rel = need_rel_for_type(type_code)
        if not rel:
            continue
        pf = graph.pathfinding_by_type(target_career, rel)
        known_inputs = _collect_known_inputs_for_type(
            state, type_code, extra_known=extra_known
        )
        apply_skills_gap_to_result(pf, known_inputs)
        by_type[type_code] = pf
    return by_type


class GraphRepositoryLike:
    """Structural typing hook for apply_skills_gap_typed (avoids circular import)."""

    def pathfinding_by_type(
        self,
        career: str,
        rel_type: str,
        *,
        known_skills: list[str] | None = None,
    ) -> PathfindingResult: ...


def merge_typed_gap_results(
    by_type: dict[str, PathfindingResult],
) -> tuple[list[CompetencyItem], list[CompetencyItem]]:
    """Aggregate known/missing items across typed pathfinding blocks."""
    known: list[CompetencyItem] = []
    missing: list[CompetencyItem] = []
    seen_known: set[tuple[str, str]] = set()
    seen_missing: set[tuple[str, str]] = set()
    for pf in by_type.values():
        for comp in pf.skills_known:
            key = (comp.kind, (comp.code or comp.name.lower()))
            if key not in seen_known:
                seen_known.add(key)
                known.append(comp)
        for comp in pf.skills_missing:
            key = (comp.kind, (comp.code or comp.name.lower()))
            if key not in seen_missing:
                seen_missing.add(key)
                missing.append(comp)
    return known, missing


def pathfinding_from_typed_gap(
    by_type: dict[str, PathfindingResult],
    *,
    career_name: str | None = None,
) -> PathfindingResult:
    """Gộp typed gap thành một PathfindingResult (roadmap / API)."""
    known, missing = merge_typed_gap_results(by_type)
    name = career_name
    if not name:
        for pf in by_type.values():
            if pf.career_name:
                name = pf.career_name
                break
    return PathfindingResult(
        found=bool(known or missing),
        career_name=name,
        competencies=known + missing,
        skills_known=known,
        skills_missing=missing,
    )


def build_gap_skill_names(
    pf: PathfindingResult,
    *,
    max_missing: int = 8,
    max_weak: int = 3,
) -> tuple[list[str], list[str]]:
    """Tên kỹ năng missing/weak từ pathfinding đã apply gap."""
    missing = [c.name for c in pf.skills_missing if c.name][:max_missing]
    missing_keys = {normalize_skill_label(n) for n in missing}

    weak_sorted = sorted(
        pf.skills_known,
        key=lambda c: (c.priority if c.priority is not None else 999, c.name),
    )
    weak: list[str] = []
    for comp in weak_sorted:
        if not comp.name:
            continue
        key = normalize_skill_label(comp.name)
        if key in missing_keys:
            continue
        weak.append(comp.name)
        if len(weak) >= max_weak:
            break
    return missing, weak


def gap_item_codes(items: Iterable[CompetencyItem]) -> list[str]:
    """Trích danh sách item_code (bỏ None) — dùng cho test đối chiếu."""
    return [c.code for c in items if c.code]


def safe_topo_sort(
    nodes: list[CompetencyItem],
    edges: list[tuple[str, str]],
) -> tuple[list[CompetencyItem], bool]:
    """
    Kahn's algorithm on in-gap subgraph only.
    edges: (src_code, dst_code) meaning src depends on dst (learn dst before src).
    Returns (ordered_nodes, had_cycle).
    """
    if not nodes:
        return [], False

    code_to_item = {c.code: c for c in nodes if c.code}
    node_codes = set(code_to_item.keys())
    in_gap_edges = [
        (s, d) for s, d in edges if s in node_codes and d in node_codes
    ]

    if not in_gap_edges:
        return list(nodes), False

    in_degree = {c: 0 for c in node_codes}
    adj: dict[str, list[str]] = {c: [] for c in node_codes}
    for src, dst in in_gap_edges:
        adj[dst].append(src)
        in_degree[src] = in_degree.get(src, 0) + 1

    queue = [c for c, deg in in_degree.items() if deg == 0]
    queue.sort(key=lambda c: (code_to_item[c].priority or 999, code_to_item[c].name))
    ordered_codes: list[str] = []

    while queue:
        n = queue.pop(0)
        ordered_codes.append(n)
        for nxt in adj.get(n, []):
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
                queue.sort(key=lambda c: (code_to_item[c].priority or 999, code_to_item[c].name))

    had_cycle = len(ordered_codes) != len(node_codes)
    if had_cycle:
        logging.getLogger(__name__).warning(
            "safe_topo_sort: cycle detected, using original order"
        )
        return list(nodes), True

    ordered = [code_to_item[c] for c in ordered_codes]
    # Append any nodes without code (shouldn't happen)
    seen = {c.code for c in ordered if c.code}
    for item in nodes:
        if item.code and item.code not in seen:
            ordered.append(item)
        elif not item.code:
            ordered.append(item)
    return ordered, False


def order_skills_by_prerequisites(
    missing: list[CompetencyItem],
    prereq_map: dict[str, list[dict]],
    known_codes: set[str],
) -> list[CompetencyItem]:
    """
    Sort missing skills by prerequisite edges (in-gap only).
    prereq_map: anchor_code -> [{code, name, rel_type}, ...] (outgoing deps).
    """
    registry = get_relation_registry()
    rel_types = set(registry.ordering_rel_types())
    missing_codes = {c.code for c in missing if c.code}

    edges: list[tuple[str, str]] = []
    for comp in missing:
        if not comp.code:
            continue
        for prereq in prereq_map.get(comp.code, []):
            if prereq.get("rel_type") not in rel_types:
                continue
            dst = str(prereq.get("code") or "")
            if dst in missing_codes:
                edges.append((comp.code, dst))
            elif dst in known_codes:
                comp.advisory_prerequisites.append(
                    f"Đã có {prereq.get('name') or dst}"
                )
            else:
                comp.advisory_prerequisites.append(
                    f"Nên học {prereq.get('name') or dst} trước {comp.name}"
                )
            if dst not in missing_codes and dst not in known_codes:
                if dst not in comp.prerequisite_codes:
                    comp.prerequisite_codes.append(dst)

    ordered, _ = safe_topo_sort(missing, edges)
    return ordered
