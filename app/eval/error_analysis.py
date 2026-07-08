"""
Phân tích lỗi D-01 — so sánh chéo cấu hình ablation theo testcase.
"""

from __future__ import annotations

from typing import Any

from app.eval.ablation_pipeline import FusionMode
from app.eval.quality_metrics import classify_error_tags, score_dict_get


def _score_key(scores: dict[str, Any], metric: str) -> float:
    return score_dict_get(scores, metric, default=0.0)


def build_per_case_matrix(
    details: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """case_id → fusion_mode → row detail."""
    matrix: dict[str, dict[str, dict[str, Any]]] = {}
    for row in details:
        cid = str(row.get("case_id") or "")
        mode = str(row.get("mode") or "")
        if not cid or not mode:
            continue
        matrix.setdefault(cid, {})[mode] = row
    return matrix


def compare_mode_wins(
    matrix: dict[str, dict[str, dict[str, Any]]],
    *,
    winner: FusionMode,
    loser: FusionMode,
    metric: str = "answer_entity_f1",
    winner_min: float = 0.3,
    loser_max: float = 0.0,
) -> list[dict[str, Any]]:
    """Các case mà winner cao hơn loser rõ rệt theo metric."""
    out: list[dict[str, Any]] = []
    w_key, l_key = winner.value, loser.value
    for case_id, modes in sorted(matrix.items()):
        w_row = modes.get(w_key)
        l_row = modes.get(l_key)
        if not w_row or not l_row:
            continue
        w_score = _score_key(w_row.get("scores") or {}, metric)
        l_score = _score_key(l_row.get("scores") or {}, metric)
        if w_score >= winner_min and l_score <= loser_max:
            out.append(
                {
                    "case_id": case_id,
                    "query": w_row.get("query") or l_row.get("query"),
                    "intent": w_row.get("intent"),
                    f"{w_key}_{metric}": w_score,
                    f"{l_key}_{metric}": l_score,
                    "winner_error_tags": w_row.get("error_tags") or [],
                    "loser_error_tags": l_row.get("error_tags") or [],
                }
            )
    return out


def build_error_analysis_report(
    details: list[dict[str, Any]],
    *,
    primary_metric: str = "answer_entity_f1",
) -> dict[str, Any]:
    """Tổng hợp win/loss và phân loại lỗi cho JSON export."""
    matrix = build_per_case_matrix(details)

    tight_vs_vector = compare_mode_wins(
        matrix,
        winner=FusionMode.TIGHT_FUSION,
        loser=FusionMode.VECTOR_ONLY,
        metric=primary_metric,
    )
    vector_vs_tight = compare_mode_wins(
        matrix,
        winner=FusionMode.VECTOR_ONLY,
        loser=FusionMode.TIGHT_FUSION,
        metric=primary_metric,
    )
    tight_vs_late = compare_mode_wins(
        matrix,
        winner=FusionMode.TIGHT_FUSION,
        loser=FusionMode.LATE_FUSION,
        winner_min=0.2,
        loser_max=0.1,
        metric=primary_metric,
    )

    by_case: list[dict[str, Any]] = []
    for case_id, modes in sorted(matrix.items()):
        entry: dict[str, Any] = {
            "case_id": case_id,
            "modes": {},
        }
        for mode_key, row in modes.items():
            scores = row.get("scores") or {}
            entry["modes"][mode_key] = {
                "answer_entity_f1": scores.get("answer_entity_f1"),
                "ontology_f1": score_dict_get(scores, "ontology_f1"),
                "off_graph_mention_rate": score_dict_get(scores, "off_graph_mention_rate"),
                "graph_entity_grounding": scores.get("graph_entity_grounding"),
                "cosine_similarity": scores.get("cosine_similarity"),
                "error_tags": row.get("error_tags") or classify_error_tags(
                    ontology_f1=score_dict_get(scores, "ontology_f1"),
                    off_graph_mention_rate=score_dict_get(scores, "off_graph_mention_rate"),
                    graph_entity_grounding=score_dict_get(scores, "graph_entity_grounding"),
                    reply=str(row.get("reply_preview") or ""),
                ),
            }
        by_case.append(entry)

    return {
        "primary_metric": primary_metric,
        "tight_fusion_beats_vector_only": tight_vs_vector,
        "vector_only_beats_tight_fusion": vector_vs_tight,
        "tight_fusion_beats_late_fusion": tight_vs_late,
        "per_case": by_case,
    }
