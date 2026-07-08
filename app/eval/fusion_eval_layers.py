"""
D-01 v4 — đánh giá ablation fusion theo lớp metric, so sánh công bằng 4 nhánh.

Lớp 1 (retrieval): F1/recall/hit trên P vs G — áp dụng cả vector_only, graph_only, late, tight.
Lớp 2 (vector baseline): chỉ vector_only — hit/recall (không dùng graph grounding).
Lớp 3 (fusion reply): answer F1 + off-graph — graph_only, late, tight (pathfinding + course_rec).
"""

from __future__ import annotations

from typing import Any, Iterable

from app.eval.ablation_pipeline import FusionMode, MODE_LABELS
from app.eval.quality_metrics import (
    QualityScores,
    _mean_optional,
    _norm_set,
    compute_quality_scores_v2,
    extract_mentions_from_reply,
    skill_f1,
    skill_recall,
)

D01_V4_GLOSSARY: dict[str, str] = {
    "retrieval_entity_f1": (
        "Lớp 1 — F1(P, G): thực thể truy xuất (Neo4j hoặc vector payload) so gold ontology. "
        "So sánh được cả 4 nhánh fusion."
    ),
    "retrieval_entity_recall": (
        "Lớp 1 — Recall(P, G) = |P∩G|/|G|. Bổ sung cho F1 khi gold nhiều phần tử."
    ),
    "retrieval_hit": (
        "Lớp 1 — 1 nếu P∩G≠∅, else 0; trung bình = HitRate entity trên tập case."
    ),
    "answer_entity_f1": (
        "Lớp 3 — F1(M, G_answer): mention trong reply so gold hiển thị "
        "(pathfinding: skill; course_rec: mã + tên khóa từ graph). "
        "Không áp dụng vector_only trong bảng fusion reply."
    ),
    "fusion_off_graph_rate": (
        "Lớp 3 — % mention reply không thuộc Neo4j. N/A với vector_only (không có graph). "
        "graph_only thường 0%."
    ),
    "graph_entity_grounding": (
        "Lớp 3 — % mention reply có trong ngữ cảnh graph. N/A với vector_only."
    ),
}

_FUSION_REPLY_MODES = frozenset(
    {FusionMode.GRAPH_ONLY, FusionMode.LATE_FUSION, FusionMode.TIGHT_FUSION}
)


def gold_retrieval_entities(item: dict[str, Any]) -> list[str]:
    """Gold cho lớp 1 — luôn đơn vị ontology (skill hoặc mã khóa)."""
    intent = str(item.get("intent") or "pathfinding")
    if intent == "course_rec":
        return list(item.get("gold_course_codes") or [])
    if intent == "competency_relation":
        return list(item.get("gold_related_codes") or [])
    return list(item.get("gold_skills") or [])


def gold_answer_entities(
    item: dict[str, Any],
    graph_snapshot: dict[str, Any] | None = None,
) -> list[str]:
    """Gold cho lớp 3 — đơn vị khớp reply (skill tên; course mã + tên)."""
    intent = str(item.get("intent") or "pathfinding")
    if intent == "pathfinding":
        return list(item.get("gold_skills") or [])
    if intent == "course_rec":
        out: list[str] = list(item.get("gold_course_codes") or [])
        out.extend(item.get("gold_course_names") or [])
        if graph_snapshot:
            gold_codes = _norm_set(item.get("gold_course_codes") or [])
            for course in graph_snapshot.get("courses") or []:
                if not isinstance(course, dict):
                    continue
                code = course.get("course_code")
                name = course.get("course_name")
                if code and _norm_set([code]) & gold_codes:
                    if code:
                        out.append(str(code))
                    if name:
                        out.append(str(name))
        return list(dict.fromkeys(out))
    if intent == "competency_relation":
        return list(item.get("gold_related_codes") or [])
    return list(item.get("gold_skills") or [])


def compute_fusion_layer_scores(
    *,
    reply: str,
    predicted_entities: Iterable[str],
    item: dict[str, Any],
    graph_context: Iterable[str],
    vector_context: Iterable[str],
    graph_snapshot: dict[str, Any] | None,
    fusion_mode: FusionMode,
) -> QualityScores:
    """
    Tính metric D-01 v4: tách gold retrieval vs gold answer; N/A metric không áp dụng theo mode.
    """
    gold_r = gold_retrieval_entities(item)
    gold_a = gold_answer_entities(item, graph_snapshot)
    predicted = list(predicted_entities)

    base = compute_quality_scores_v2(
        reply=reply,
        predicted_entities=predicted,
        gold_entities=gold_r,
        graph_context=graph_context,
        vector_context=vector_context,
        graph_snapshot=graph_snapshot,
        no_mention_policy="penalize",
    )

    graph_ctx = _norm_set(graph_context)
    vector_ctx = _norm_set(vector_context)
    vocab = set(graph_ctx) | vector_ctx
    vocab |= _norm_set(predicted)
    vocab |= _norm_set(gold_r)
    vocab |= _norm_set(gold_a)

    mentions = extract_mentions_from_reply(reply, vocab)
    if not mentions:
        mentions = _norm_set(predicted)

    answer_f1 = skill_f1(mentions, gold_a)
    recall, n_pred, n_gold = skill_recall(predicted, gold_r)
    pred_set = _norm_set(predicted)
    gold_r_set = _norm_set(gold_r)
    hit = 1.0 if (pred_set & gold_r_set) else (1.0 if not gold_r_set else 0.0)

    graph_gr = base.graph_grounding_rate
    fusion_off_graph = base.hallucination_rate
    vector_only_mention = base.vector_only_mention_rate

    if fusion_mode == FusionMode.VECTOR_ONLY:
        graph_gr = None
        fusion_off_graph = None
    if fusion_mode == FusionMode.GRAPH_ONLY:
        vector_only_mention = None

    onto = base.ontology_f1 if base.ontology_f1 is not None else base.skill_accuracy

    return QualityScores(
        faithfulness=base.faithfulness,
        skill_accuracy=onto,
        hallucination_rate=fusion_off_graph if fusion_off_graph is not None else 0.0,
        n_predicted=n_pred,
        n_gold=n_gold,
        n_hallucinated=base.n_hallucinated,
        n_mentions=base.n_mentions,
        ontology_f1=onto,
        answer_entity_f1=answer_f1,
        full_grounding_rate=base.full_grounding_rate,
        graph_grounding_rate=graph_gr,
        exclusive_graph_rate=base.exclusive_graph_rate,
        vector_only_mention_rate=vector_only_mention,
        relation_code_recall=base.relation_code_recall,
        claim_grounding_rate=base.claim_grounding_rate,
        no_mention_case=base.no_mention_case,
        retrieval_entity_recall=recall,
        retrieval_hit=hit,
        fusion_off_graph_rate=fusion_off_graph,
    )


def _scores_v4_export(scores: QualityScores) -> dict[str, float | int | None | bool]:
    onto = scores.ontology_f1 if scores.ontology_f1 is not None else scores.skill_accuracy
    return {
        "retrieval_entity_f1": round(onto, 4) if onto is not None else None,
        "retrieval_entity_recall": (
            round(scores.retrieval_entity_recall, 4)
            if scores.retrieval_entity_recall is not None
            else None
        ),
        "retrieval_hit": (
            round(scores.retrieval_hit, 4) if scores.retrieval_hit is not None else None
        ),
        "answer_entity_f1": (
            round(scores.answer_entity_f1, 4) if scores.answer_entity_f1 is not None else None
        ),
        "fusion_off_graph_rate": (
            round(scores.fusion_off_graph_rate, 4)
            if scores.fusion_off_graph_rate is not None
            else None
        ),
        "graph_entity_grounding": (
            round(scores.graph_grounding_rate, 4)
            if scores.graph_grounding_rate is not None
            else None
        ),
        "vector_only_mention_rate": (
            round(scores.vector_only_mention_rate, 4)
            if scores.vector_only_mention_rate is not None
            else None
        ),
        "n_predicted": scores.n_predicted,
        "n_gold": scores.n_gold,
        "n_mentions": scores.n_mentions,
        "no_mention_case": scores.no_mention_case,
    }


def average_layer_scores(rows: list[QualityScores]) -> dict[str, float | None]:
    if not rows:
        return {}
    onto = [r.ontology_f1 if r.ontology_f1 is not None else r.skill_accuracy for r in rows]
    return {
        "retrieval_entity_f1": _mean_optional(onto),
        "retrieval_entity_recall": _mean_optional(
            [r.retrieval_entity_recall for r in rows]
        ),
        "retrieval_hit": _mean_optional([r.retrieval_hit for r in rows]),
        "answer_entity_f1": _mean_optional([r.answer_entity_f1 for r in rows]),
        "fusion_off_graph_rate": _mean_optional(
            [r.fusion_off_graph_rate for r in rows]
        ),
        "graph_entity_grounding": _mean_optional([r.graph_grounding_rate for r in rows]),
        "vector_only_mention_rate": _mean_optional(
            [r.vector_only_mention_rate for r in rows]
        ),
        "n_cases": float(len(rows)),
    }


def summarize_v4_layers(
    details: list[dict[str, Any]],
    *,
    modes: list[FusionMode],
) -> dict[str, Any]:
    """Tổng hợp 3 lớp metric cho báo cáo / luận văn."""
    layer1: dict[str, dict[str, float | None]] = {}
    layer3_all: dict[str, dict[str, float | None]] = {}
    layer3_pathfinding: dict[str, dict[str, float | None]] = {}
    layer3_course_rec: dict[str, dict[str, float | None]] = {}

    by_mode_intent: dict[tuple[str, str], list[dict]] = {}
    for row in details:
        mode = str(row.get("mode") or "")
        intent = str(row.get("intent") or "unknown")
        by_mode_intent.setdefault((mode, intent), []).append(row.get("scores") or {})

    def _avg_from_score_dicts(
        score_dicts: list[dict],
        keys: tuple[str, ...],
    ) -> dict[str, float | None]:
        out: dict[str, list[float]] = {k: [] for k in keys}
        for sd in score_dicts:
            for k in keys:
                v = sd.get(k)
                if v is not None:
                    out[k].append(float(v))
        return {
            k: round(sum(v) / len(v), 4) if v else None for k, v in out.items()
        }

    v4_keys = (
        "retrieval_entity_f1",
        "retrieval_entity_recall",
        "retrieval_hit",
        "answer_entity_f1",
        "fusion_off_graph_rate",
        "graph_entity_grounding",
    )

    for mode in modes:
        mkey = mode.value
        all_scores: list[dict] = []
        for (mode_k, _intent), sds in by_mode_intent.items():
            if mode_k != mkey:
                continue
            all_scores.extend(sds)
        if not all_scores:
            continue
        layer1[mkey] = _avg_from_score_dicts(
            all_scores,
            ("retrieval_entity_f1", "retrieval_entity_recall", "retrieval_hit"),
        )
        layer1[mkey]["n_cases"] = len(all_scores)  # type: ignore[assignment]

        if mode not in _FUSION_REPLY_MODES:
            continue
        layer3_all[mkey] = _avg_from_score_dicts(
            all_scores,
            ("answer_entity_f1", "fusion_off_graph_rate", "graph_entity_grounding"),
        )
        layer3_all[mkey]["n_cases"] = len(all_scores)  # type: ignore[assignment]

        pf_scores = by_mode_intent.get((mkey, "pathfinding"), [])
        if pf_scores:
            layer3_pathfinding[mkey] = _avg_from_score_dicts(
                pf_scores,
                ("answer_entity_f1", "fusion_off_graph_rate", "graph_entity_grounding"),
            )
            layer3_pathfinding[mkey]["n_cases"] = len(pf_scores)  # type: ignore[assignment]

        cr_scores = by_mode_intent.get((mkey, "course_rec"), [])
        if cr_scores:
            layer3_course_rec[mkey] = _avg_from_score_dicts(
                cr_scores,
                (
                    "retrieval_entity_f1",
                    "answer_entity_f1",
                    "fusion_off_graph_rate",
                ),
            )
            layer3_course_rec[mkey]["n_cases"] = len(cr_scores)  # type: ignore[assignment]

    return {
        "layer1_retrieval_all_intents": layer1,
        "layer3_fusion_reply_all_intents": layer3_all,
        "layer3_fusion_reply_pathfinding": layer3_pathfinding,
        "layer3_fusion_reply_course_rec": layer3_course_rec,
    }


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.2f}\\%"


def _fmt_f1(val: float | None) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.2f}\\%"


def format_latex_v4_tables(
    layer_summary: dict[str, Any],
    *,
    eval_run_mode: str = "static",
) -> str:
    """Hai bảng LaTeX: lớp 1 (4 mode) + lớp 3 pathfinding (3 mode có graph)."""
    l1 = layer_summary.get("layer1_retrieval_all_intents") or {}
    l3pf = layer_summary.get("layer3_fusion_reply_pathfinding") or {}

    lines = [
        "% D-01 v4 — Layer 1: retrieval entity (4 fusion modes)",
        r"\begin{table}[ht]",
        r"\centering",
        rf"\caption{{D-01 v4 — Lớp 1: Entity recall truy xuất $F_1(P,G)$ (mode={eval_run_mode})}}",
        r"\label{tab:ablation-v4-layer1}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Chế độ & Retrieval F1 & Recall & Hit rate \\",
        r"\midrule",
    ]
    for mode in FusionMode:
        mkey = mode.value
        if mkey not in l1:
            continue
        row = l1[mkey]
        lines.append(
            f"{MODE_LABELS[mode]} & "
            f"{_fmt_f1(row.get('retrieval_entity_f1'))} & "
            f"{_fmt_f1(row.get('retrieval_entity_recall'))} & "
            f"{_fmt_f1(row.get('retrieval_hit'))} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])

    lines.extend(
        [
            "% D-01 v4 — Layer 3: fusion reply (pathfinding, graph modes)",
            r"\begin{table}[ht]",
            r"\centering",
            rf"\caption{{D-01 v4 — Lớp 3: Reply pathfinding (mode={eval_run_mode})}}",
            r"\label{tab:ablation-v4-layer3-pf}",
            r"\begin{tabular}{lrrr}",
            r"\toprule",
            r"Chế độ & Answer Entity F1 & Off-graph & Graph grounding \\",
            r"\midrule",
        ]
    )
    for mode in (FusionMode.GRAPH_ONLY, FusionMode.LATE_FUSION, FusionMode.TIGHT_FUSION):
        mkey = mode.value
        if mkey not in l3pf:
            continue
        row = l3pf[mkey]
        lines.append(
            f"{MODE_LABELS[mode]} & "
            f"{_fmt_f1(row.get('answer_entity_f1'))} & "
            f"{_fmt_pct(row.get('fusion_off_graph_rate'))} & "
            f"{_fmt_pct(row.get('graph_entity_grounding'))} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines)
