"""
Ablation chất lượng D-01 — so sánh 4 cấu hình Graph-RAG (hybrid evaluation).

Chạy:
  python scripts/build_answer_gold.py
  python scripts/run_quality_ablation.py
  python scripts/run_quality_ablation.py --modes tight_fusion,late_fusion,vector_only
  python scripts/run_quality_ablation.py --eval-mode generative --limit 5
  python scripts/run_quality_ablation.py --json-out results/ablation_d01.json

Bốn fusion mode:
  (A) vector_only  — chỉ Qdrant
  (B) graph_only   — chỉ Neo4j
  (C) late_fusion  — graph + vector song song, không seed
  (D) tight_fusion — graph dẫn hướng bởi vector seeds (A-01)

Eval mode:
  static (mặc định) — formatter tĩnh, nhanh
  generative        — LLM sinh câu trả lời + cosine similarity vs gold reference
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

DEFAULT_GOLD = PROJECT_ROOT / "data" / "eval" / "answer_gold.jsonl"

from app.eval.ablation_pipeline import (  # noqa: E402
    AblationPipeline,
    EvalRunMode,
    FusionMode,
    MODE_LABELS,
)
from app.eval.error_analysis import build_error_analysis_report  # noqa: E402
from app.eval.fusion_eval_layers import (  # noqa: E402
    D01_V4_GLOSSARY,
    format_latex_v4_tables,
    summarize_v4_layers,
)
from app.eval.quality_metrics import D01_V3_GLOSSARY, QualityScores, average_scores  # noqa: E402
from app.eval.statistics import (  # noqa: E402
    bootstrap_ci,
    compare_groups_effect,
    rank_biserial_effect_size,
)

ALPHA = 0.05

V2_METRICS = (
    "answer_entity_f1",
    "exclusive_graph_rate",
    "ontology_f1",
    "hallucination_rate",
)

V3_METRICS = (
    "answer_entity_f1",
    "ontology_f1",
    "graph_entity_grounding",
    "off_graph_mention_rate",
)

V4_METRICS = (
    "retrieval_entity_f1",
    "retrieval_entity_recall",
    "retrieval_hit",
    "answer_entity_f1",
    "fusion_off_graph_rate",
    "graph_entity_grounding",
)

D01_PRIMARY_METRIC = "answer_entity_f1"
D01_V4_PRIMARY_METRIC = "retrieval_entity_f1"


def _export_profile(metrics_profile: str) -> str:
    if metrics_profile in ("v3", "v4", "v2", "v1"):
        return metrics_profile
    return "internal"


def _summary_export_dict(scores: QualityScores, metrics_profile: str) -> dict[str, Any]:
    profile = _export_profile(metrics_profile)
    if profile == "internal":
        return scores.as_dict("internal")
    return scores.as_dict(profile)  # type: ignore[arg-type]

DERIVED_GOLD_SOURCES = frozenset(
    {"derived_from_graph_repository", "derived_from_retrieval_v2"}
)
INDEPENDENT_GOLD_SOURCES = frozenset({"human_verified_from_excel", "excel_derived"})


def _filter_cases_by_gold_source(
    cases: list[dict],
    gold_source: str | None,
) -> list[dict]:
    if not gold_source or gold_source == "all":
        return cases
    if gold_source == "independent":
        return [c for c in cases if str(c.get("gold_source") or "") in INDEPENDENT_GOLD_SOURCES]
    if gold_source == "derived":
        return [
            c
            for c in cases
            if str(c.get("gold_source") or "") in DERIVED_GOLD_SOURCES
            or not c.get("gold_source")
        ]
    raise ValueError(f"Unknown gold_source filter: {gold_source}")


def _dual_gold_comparison_row(
    derived_report: dict[str, Any],
    independent_report: dict[str, Any],
    *,
    metric: str = "answer_entity_f1",
) -> dict[str, Any]:
    """Compare primary metric between derived (regression) and independent (thesis) gold."""
    derived_summary = derived_report.get("summary") or {}
    indep_summary = independent_report.get("summary") or {}
    row: dict[str, Any] = {"metric": metric, "modes": {}}
    for mode_key in derived_summary:
        d_val = (derived_summary.get(mode_key) or {}).get(metric)
        i_val = (indep_summary.get(mode_key) or {}).get(metric)
        if d_val is None and i_val is None:
            continue
        delta = None
        if d_val is not None and i_val is not None:
            delta = round(float(i_val) - float(d_val), 4)
        row["modes"][mode_key] = {
            "derived": d_val,
            "independent": i_val,
            "delta_independent_minus_derived": delta,
        }
    row["derived_n"] = derived_report.get("n_cases")
    row["independent_n"] = independent_report.get("n_cases")
    return row


def _load_gold(path: Path) -> list[dict]:
    if not path.is_file():
        print(f"ERROR: missing {path}")
        print("Run: python scripts/build_answer_gold.py")
        sys.exit(1)
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _stratification_key(case: dict, fields: tuple[str, ...]) -> str:
    parts: list[str] = []
    for field in fields:
        val = case.get(field)
        if val is None and field == "career":
            val = case.get("competency")
        parts.append(str(val or "_"))
    return "|".join(parts)


def _stratified_sample(
    cases: list[dict],
    size: int,
    *,
    seed: int,
    sample_by: tuple[str, ...],
) -> list[dict]:
    if size <= 0 or size >= len(cases):
        return list(cases)
    rng = random.Random(seed)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        buckets[_stratification_key(case, sample_by)].append(case)

    selected: list[dict] = []
    remaining = size
    groups = sorted(buckets.items(), key=lambda kv: -len(kv[1]))
    total = len(cases)

    for idx, (_key, group) in enumerate(groups):
        if remaining <= 0:
            break
        if idx == len(groups) - 1:
            take = min(remaining, len(group))
        else:
            take = min(len(group), remaining, max(1, round(size * len(group) / total)))
        rng.shuffle(group)
        selected.extend(group[:take])
        remaining -= take

    if len(selected) < size:
        picked = {id(c) for c in selected}
        pool = [c for c in cases if id(c) not in picked]
        rng.shuffle(pool)
        selected.extend(pool[: size - len(selected)])
    rng.shuffle(selected)
    return selected[:size]


def _bootstrap_gold_labels(cases: list[dict]) -> list[dict]:
    from app.graph.repository import GraphRepository

    graph = GraphRepository()
    if not graph._client.available:
        graph.close()
        return cases

    out: list[dict] = []
    for item in cases:
        row = dict(item)
        if row.get("intent") == "pathfinding" and not row.get("gold_skills"):
            pf = graph.pathfinding(str(row.get("career") or ""))
            if pf.found:
                row["gold_skills"] = [c.name for c in pf.competencies]
        if row.get("intent") == "course_rec" and not row.get("gold_course_codes"):
            cr = graph.course_recommendation(str(row.get("competency") or ""))
            if cr.found:
                row["gold_course_codes"] = [
                    c.course_code for c in cr.courses if c.course_code
                ]
        out.append(row)
    graph.close()
    return out


def _parse_fusion_modes(raw: str | None) -> list[FusionMode]:
    if not raw:
        return list(FusionMode)
    modes: list[FusionMode] = []
    for part in raw.split(","):
        part = part.strip().lower()
        if not part:
            continue
        modes.append(FusionMode(part))
    return modes or list(FusionMode)


def _parse_eval_mode(raw: str) -> EvalRunMode:
    key = (raw or "static").strip().lower()
    return EvalRunMode(key)


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def _paired_metric_vectors(
    details: list[dict[str, Any]],
    *,
    mode_a: FusionMode,
    mode_b: FusionMode,
    metric: str,
) -> tuple[list[float], list[float], list[str]]:
    """Ghép điểm theo case_id cho hai cấu hình."""
    by_case: dict[str, dict[str, float]] = {}
    case_order: list[str] = []
    for row in details:
        cid = str(row.get("case_id") or "")
        mode = str(row.get("mode") or "")
        if not cid:
            continue
        if cid not in by_case:
            by_case[cid] = {}
            case_order.append(cid)
        scores = row.get("scores") or {}
        by_case[cid][mode] = float(scores.get(metric) or 0.0)

    a_key, b_key = mode_a.value, mode_b.value
    a_vals: list[float] = []
    b_vals: list[float] = []
    paired_ids: list[str] = []
    for cid in case_order:
        modes = by_case.get(cid) or {}
        if a_key not in modes or b_key not in modes:
            continue
        a_vals.append(modes[a_key])
        b_vals.append(modes[b_key])
        paired_ids.append(cid)
    return a_vals, b_vals, paired_ids


def run_significance_tests(
    details: list[dict[str, Any]],
    *,
    baseline_modes: list[FusionMode] | None = None,
    metrics: list[str] | None = None,
) -> dict[str, Any]:
    """
    Paired t-test và Wilcoxon signed-rank: Tight Fusion vs baseline.
    """
    try:
        from scipy import stats
    except ImportError:
        return {
            "available": False,
            "error": "scipy not installed — pip install scipy",
        }

    baselines = baseline_modes or [
        FusionMode.LATE_FUSION,
        FusionMode.VECTOR_ONLY,
    ]
    metric_names = metrics or ["faithfulness", "skill_accuracy"]
    target = FusionMode.TIGHT_FUSION
    results: dict[str, Any] = {"available": True, "alpha": ALPHA, "comparisons": []}

    for baseline in baselines:
        if baseline == target:
            continue
        for metric in metric_names:
            a_vals, b_vals, case_ids = _paired_metric_vectors(
                details,
                mode_a=target,
                mode_b=baseline,
                metric=metric,
            )
            if len(a_vals) < 2:
                results["comparisons"].append(
                    {
                        "target": target.value,
                        "baseline": baseline.value,
                        "metric": metric,
                        "n_pairs": len(a_vals),
                        "skipped": True,
                        "reason": "insufficient paired samples",
                    }
                )
                continue

            t_stat, t_p = stats.ttest_rel(a_vals, b_vals)
            try:
                w_stat, w_p = stats.wilcoxon(a_vals, b_vals)
            except ValueError:
                w_stat, w_p = float("nan"), float("nan")

            mean_diff = sum(a - b for a, b in zip(a_vals, b_vals)) / len(a_vals)
            significant = bool(t_p < ALPHA) if t_p == t_p else False

            mean_a, ci_lo_a, ci_hi_a = bootstrap_ci(a_vals)
            mean_b, ci_lo_b, ci_hi_b = bootstrap_ci(b_vals)
            results["comparisons"].append(
                {
                    "target": target.value,
                    "baseline": baseline.value,
                    "metric": metric,
                    "n_pairs": len(a_vals),
                    "mean_target": round(mean_a, 4),
                    "ci_target": [round(ci_lo_a, 4), round(ci_hi_a, 4)],
                    "mean_baseline": round(mean_b, 4),
                    "ci_baseline": [round(ci_lo_b, 4), round(ci_hi_b, 4)],
                    "effect_size_rank_biserial": round(
                        rank_biserial_effect_size(a_vals, b_vals), 4
                    ),
                    "effect": compare_groups_effect(b_vals, a_vals),
                    "mean_diff_target_minus_baseline": round(mean_diff, 4),
                    "paired_ttest": {
                        "t_statistic": round(float(t_stat), 4),
                        "p_value": round(float(t_p), 6),
                        "significant_at_alpha": significant,
                    },
                    "wilcoxon": {
                        "statistic": round(float(w_stat), 4) if w_stat == w_stat else None,
                        "p_value": round(float(w_p), 6) if w_p == w_p else None,
                    },
                    "sample_case_ids": case_ids[:5],
                }
            )
    return results


def export_stratified_breakdown_csv(
    details: list[dict[str, Any]],
    path: Path,
    *,
    metric: str = "answer_entity_f1",
) -> None:
    """D-06 — CSV rows: stratification_key, mode, n, mean_metric."""
    import csv

    buckets: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for row in details:
        mode = str(row.get("mode") or "")
        meta = row.get("meta") or {}
        intent = str(row.get("intent") or "")
        hint = "hint" if meta.get("entity_hint", True) is not False else "no_hint"
        difficulty = str(meta.get("query_difficulty") or "unknown")
        val = (row.get("scores") or {}).get(metric)
        if val is None:
            continue
        buckets[(intent, hint, difficulty, mode)].append(float(val))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["intent", "entity_hint", "query_difficulty", "mode", "n", metric],
        )
        writer.writeheader()
        for key in sorted(buckets.keys()):
            intent, hint, difficulty, mode = key
            vals = buckets[key]
            writer.writerow(
                {
                    "intent": intent,
                    "entity_hint": hint,
                    "query_difficulty": difficulty,
                    "mode": mode,
                    "n": len(vals),
                    metric: round(sum(vals) / len(vals), 4) if vals else 0.0,
                }
            )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_latex_table_v3(
    summary: dict[FusionMode, QualityScores],
    *,
    eval_run_mode: EvalRunMode,
    significance: dict[str, Any] | None = None,
    table_label: str = "tab:ablation-quality-v3",
) -> str:
    """Bảng luận văn D-01 v3 — không dùng faithfulness/hallucination (tránh nhầm D-03)."""
    has_cosine = any(s.cosine_similarity is not None for s in summary.values())
    cols = "lrrrrr" if has_cosine else "lrrrr"
    header = (
        r"Cau hinh & Answer Entity F1 & Ontology F1 & Graph Grounding & Off-Graph Mention (\%)"
        + (r" & Cosine Sim." if has_cosine else "")
        + r" \\"
    )
    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        rf"\caption{{D-01 ablation (mode={eval_run_mode.value}) — metric v3, formatter static}}",
        rf"\label{{{table_label}}}",
        rf"\begin{{tabular}}{{{cols}}}",
        r"\toprule",
        header,
        r"\midrule",
    ]
    order = [
        FusionMode.VECTOR_ONLY,
        FusionMode.GRAPH_ONLY,
        FusionMode.LATE_FUSION,
        FusionMode.TIGHT_FUSION,
    ]
    for mode in order:
        if mode not in summary:
            continue
        s = summary[mode]
        exported = s.as_d01_v3_dict()
        ans = exported.get("answer_entity_f1")
        onto = exported.get("ontology_f1")
        graph_gr = exported.get("graph_entity_grounding")
        off_graph = exported.get("off_graph_mention_rate")
        row = (
            f"{MODE_LABELS[mode]} & "
            f"{ans:.3f} & {onto:.3f} & "
            f"{graph_gr:.3f} & {float(off_graph or 0) * 100:.1f}"
        )
        if has_cosine:
            cos = s.cosine_similarity
            row += f" & {cos:.3f}" if cos is not None else " & --"
        row += r" \\"
        lines.append(row)
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    if significance and significance.get("available") and significance.get("comparisons"):
        notes: list[str] = []
        for comp in significance["comparisons"]:
            if comp.get("skipped"):
                continue
            t = comp.get("paired_ttest") or {}
            p = t.get("p_value")
            t_stat = t.get("t_statistic")
            sig = t.get("significant_at_alpha")
            if p is None or p != p:
                continue
            notes.append(
                rf"TightFusion vs {comp['baseline']} ({comp['metric']}): "
                rf"$t={t_stat}$, $p={p}$"
                + (r", significant at $\alpha=0.05$." if sig else r".")
            )
        if notes:
            lines.append(r"\begin{tablenotes}\small")
            for note in notes:
                lines.append(rf"\item {note}")
            lines.append(r"\end{tablenotes}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def _format_latex_table_v2(
    summary: dict[FusionMode, QualityScores],
    *,
    eval_run_mode: EvalRunMode,
    significance: dict[str, Any] | None = None,
    table_label: str = "tab:ablation-quality-v2",
) -> str:
    has_cosine = any(s.cosine_similarity is not None for s in summary.values())
    cols = "lrrrrr" if has_cosine else "lrrrr"
    header = (
        r"Cau hinh & Answer Entity F1 & Exclusive Graph & Ontology F1 & Hallucination (\%)"
        + (r" & Cosine Sim." if has_cosine else "")
        + r" \\"
    )
    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        rf"\caption{{D-01 V2 metrics (mode={eval_run_mode.value})}}",
        rf"\label{{{table_label}}}",
        rf"\begin{{tabular}}{{{cols}}}",
        r"\toprule",
        header,
        r"\midrule",
    ]
    order = [
        FusionMode.VECTOR_ONLY,
        FusionMode.GRAPH_ONLY,
        FusionMode.LATE_FUSION,
        FusionMode.TIGHT_FUSION,
    ]
    for mode in order:
        if mode not in summary:
            continue
        s = summary[mode]
        ans = s.answer_entity_f1 if s.answer_entity_f1 is not None else s.skill_accuracy
        excl = s.exclusive_graph_rate if s.exclusive_graph_rate is not None else 0.0
        onto = s.ontology_f1 if s.ontology_f1 is not None else s.skill_accuracy
        row = (
            f"{MODE_LABELS[mode]} & {ans:.3f} & {excl:.3f} & {onto:.3f} "
            f"& {s.hallucination_rate * 100:.1f}"
        )
        if has_cosine:
            cos = s.cosine_similarity
            row += f" & {cos:.3f}" if cos is not None else " & --"
        row += r" \\"
        lines.append(row)
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def _format_latex_table(
    summary: dict[FusionMode, QualityScores],
    *,
    eval_run_mode: EvalRunMode,
    significance: dict[str, Any] | None = None,
    table_label: str = "tab:ablation-quality",
    metrics_profile: str = "v3",
) -> str:
    if metrics_profile == "v3":
        return _format_latex_table_v3(
            summary,
            eval_run_mode=eval_run_mode,
            significance=significance,
            table_label=table_label if table_label.endswith("v3") else "tab:ablation-quality-v3",
        )
    if metrics_profile == "v2":
        return _format_latex_table_v2(
            summary,
            eval_run_mode=eval_run_mode,
            significance=significance,
            table_label=table_label,
        )
    has_cosine = any(
        s.cosine_similarity is not None for s in summary.values()
    )
    cols = "lrrrr" if has_cosine else "lrrr"
    header = (
        r"Cau hinh & Faithfulness & Skill Accuracy & Hallucination Rate (\%)"
        + (r" & Cosine Sim." if has_cosine else "")
        + r" \\"
    )

    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        rf"\caption{{So sanh chat luong Graph-RAG (D-01, mode={eval_run_mode.value})}}",
        rf"\label{{{table_label}}}",
        rf"\begin{{tabular}}{{{cols}}}",
        r"\toprule",
        header,
        r"\midrule",
    ]
    order = [
        FusionMode.VECTOR_ONLY,
        FusionMode.GRAPH_ONLY,
        FusionMode.LATE_FUSION,
        FusionMode.TIGHT_FUSION,
    ]
    for mode in order:
        if mode not in summary:
            continue
        s = summary[mode]
        label = MODE_LABELS[mode]
        row = (
            f"{label} & {s.faithfulness:.3f} & {s.skill_accuracy:.3f} "
            f"& {s.hallucination_rate * 100:.1f}"
        )
        if has_cosine:
            cos = s.cosine_similarity
            row += f" & {cos:.3f}" if cos is not None else " & --"
        row += r" \\"
        lines.append(row)

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")

    if significance and significance.get("available") and significance.get("comparisons"):
        notes: list[str] = []
        for comp in significance["comparisons"]:
            if comp.get("skipped"):
                continue
            t = comp.get("paired_ttest") or {}
            p = t.get("p_value")
            t_stat = t.get("t_statistic")
            sig = t.get("significant_at_alpha")
            if p is None or p != p:
                continue
            notes.append(
                rf"TightFusion vs {comp['baseline']} ({comp['metric']}): "
                rf"$t={t_stat}$, $p={p}$"
                + (r", significant at $\alpha=0.05$." if sig else r".")
            )
        if notes:
            lines.append(r"\begin{tablenotes}\small")
            for note in notes:
                lines.append(rf"\item {note}")
            lines.append(r"\end{tablenotes}")

    lines.append(r"\end{table}")
    return "\n".join(lines)


def summarize_by_intent(
    details: list[dict[str, Any]],
    *,
    modes: list[FusionMode],
    metrics_profile: str = "v4",
) -> dict[str, dict[str, dict[str, float]]]:
    """Trung bình metric theo intent × fusion mode."""
    if metrics_profile == "v4":
        keys = (
            "retrieval_entity_f1",
            "retrieval_entity_recall",
            "retrieval_hit",
            "answer_entity_f1",
            "fusion_off_graph_rate",
            "graph_entity_grounding",
        )
    elif metrics_profile == "v3":
        keys = (
            "answer_entity_f1",
            "ontology_f1",
            "graph_entity_grounding",
            "off_graph_mention_rate",
        )
    elif metrics_profile == "v2":
        keys = (
            "answer_entity_f1",
            "ontology_f1",
            "exclusive_graph_rate",
            "hallucination_rate",
        )
    else:
        keys = ("faithfulness", "skill_accuracy", "hallucination_rate")

    buckets: dict[str, dict[str, list[float]]] = {}
    for row in details:
        intent = str(row.get("intent") or "unknown")
        mode = str(row.get("mode") or "")
        scores = row.get("scores") or {}
        buckets.setdefault(intent, {}).setdefault(mode, {k: [] for k in keys})
        for key in keys:
            if key in scores and scores[key] is not None:
                buckets[intent][mode][key].append(float(scores[key]))

    out: dict[str, dict[str, dict[str, float]]] = {}
    for intent, mode_map in sorted(buckets.items()):
        out[intent] = {}
        for mode in modes:
            mkey = mode.value
            if mkey not in mode_map:
                continue
            vals = mode_map[mkey]
            out[intent][mkey] = {
                k: round(sum(v) / len(v), 4) if v else 0.0
                for k, v in vals.items()
            }
    return out


def summarize_by_cypher_matched(
    details: list[dict[str, Any]],
    *,
    modes: list[FusionMode],
) -> dict[str, Any]:
    """Aggregate metrics by Easy/Hard no-hint (cypher_matched true/false)."""
    buckets: dict[str, dict[str, list[dict[str, float | None]]]] = {
        "easy": {},
        "hard": {},
        "unknown": {},
    }
    metric_keys = (
        "answer_entity_f1",
        "ontology_f1",
        "exclusive_graph_rate",
        "faithfulness",
        "skill_accuracy",
        "hallucination_rate",
    )

    for row in details:
        meta = row.get("meta") or {}
        if meta.get("entity_hint", True) is not False:
            continue
        matched = meta.get("cypher_matched")
        if matched is True:
            group = "easy"
        elif matched is False:
            group = "hard"
        else:
            group = "unknown"
        mode = str(row.get("mode") or "")
        scores = row.get("scores") or {}
        buckets[group].setdefault(mode, {k: [] for k in metric_keys})
        for key in metric_keys:
            val = scores.get(key)
            if val is not None:
                buckets[group][mode][key].append(float(val))

    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 4) if vals else None

    out: dict[str, Any] = {}
    for group, mode_map in buckets.items():
        if not mode_map:
            continue
        out[group] = {"n_cases": 0, "by_mode": {}}
        case_ids: set[str] = set()
        for row in details:
            meta = row.get("meta") or {}
            if meta.get("entity_hint", True) is not False:
                continue
            matched = meta.get("cypher_matched")
            g = "easy" if matched is True else "hard" if matched is False else "unknown"
            if g == group:
                case_ids.add(str(row.get("case_id") or ""))
        out[group]["n_cases"] = len(case_ids)
        for mode in modes:
            mkey = mode.value
            if mkey not in mode_map:
                continue
            vals = mode_map[mkey]
            out[group]["by_mode"][mkey] = {
                k: _avg(v) for k, v in vals.items() if v
            }
    return out


def run_ablation(
    *,
    gold_path: Path,
    modes: list[FusionMode],
    limit: int | None,
    bootstrap_gold: bool,
    eval_run_mode: EvalRunMode,
    metrics_profile: str = "v3",
    snapshot_date: str | None = None,
    intents: set[str] | None = None,
    sample_strategy: str | None = None,
    sample_size: int | None = None,
    sample_seed: int = 42,
    sample_by: tuple[str, ...] = ("intent", "career"),
    gold_source: str | None = None,
    kg_snapshot: str | None = None,
) -> dict:
    cases = _load_gold(gold_path)
    cases = _filter_cases_by_gold_source(cases, gold_source)
    if intents:
        cases = [c for c in cases if str(c.get("intent") or "") in intents]
    if bootstrap_gold:
        cases = _bootstrap_gold_labels(cases)
    if sample_strategy == "stratified" and sample_size is not None:
        cases = _stratified_sample(
            cases, sample_size, seed=sample_seed, sample_by=sample_by
        )
    elif limit is not None:
        cases = cases[: max(0, limit)]

    export_profile = _export_profile(metrics_profile)
    primary_metric = (
        D01_V4_PRIMARY_METRIC
        if metrics_profile == "v4"
        else D01_PRIMARY_METRIC
        if metrics_profile in ("v2", "v3")
        else "faithfulness"
    )

    pipeline = AblationPipeline(
        eval_run_mode=eval_run_mode,
        metrics_profile=metrics_profile if metrics_profile in ("v3", "v4") else "v4",
    )
    per_mode_scores: dict[FusionMode, list[QualityScores]] = {m: [] for m in modes}
    detail_rows: list[dict] = []

    n_cases = len(cases)
    total_steps = n_cases * len(modes)
    step = 0
    try:
        for case_idx, case in enumerate(cases, start=1):
            case_id = str(case.get("id") or case.get("query", "")[:40])
            for mode in modes:
                step += 1
                print(
                    f"[{step}/{total_steps}] case {case_idx}/{n_cases} "
                    f"id={case_id} mode={mode.value} eval={eval_run_mode.value}",
                    flush=True,
                )
                result = pipeline.run_case(case, mode)
                per_mode_scores[mode].append(result.scores)
                detail_rows.append(result.as_dict(export_profile))
    finally:
        pipeline.close()

    summary = {mode: average_scores(per_mode_scores[mode]) for mode in modes}
    sig_metrics = (
        list(V4_METRICS)
        if metrics_profile == "v4"
        else list(V3_METRICS)
        if metrics_profile == "v3"
        else list(V2_METRICS)
        if metrics_profile == "v2"
        else ["faithfulness", "skill_accuracy"]
    )
    significance = run_significance_tests(detail_rows, metrics=sig_metrics)
    error_analysis = build_error_analysis_report(detail_rows, primary_metric=primary_metric)
    by_intent = summarize_by_intent(detail_rows, modes=modes, metrics_profile=metrics_profile)
    by_cypher = summarize_by_cypher_matched(detail_rows, modes=modes)

    table_label = (
        "tab:ablation-quality-generative-v3"
        if eval_run_mode == EvalRunMode.GENERATIVE and metrics_profile == "v3"
        else "tab:ablation-quality-generative-v2"
        if eval_run_mode == EvalRunMode.GENERATIVE and metrics_profile == "v2"
        else "tab:ablation-quality-generative"
        if eval_run_mode == EvalRunMode.GENERATIVE
        else "tab:ablation-quality-v3"
        if metrics_profile == "v3"
        else "tab:ablation-quality-v2"
        if metrics_profile == "v2"
        else "tab:ablation-quality"
    )

    report: dict[str, Any] = {
        "n_cases": len(cases),
        "eval_run_mode": eval_run_mode.value,
        "metrics_profile": metrics_profile,
        "primary_metric": primary_metric,
        "metric_glossary": (
            D01_V4_GLOSSARY
            if metrics_profile == "v4"
            else D01_V3_GLOSSARY
            if metrics_profile == "v3"
            else None
        ),
        "modes": [m.value for m in modes],
        "summary_by_intent": by_intent,
        "summary_by_cypher_matched": by_cypher,
        "summary": {
            MODE_LABELS[mode]: _summary_export_dict(summary[mode], metrics_profile)
            for mode in modes
        },
        "significance_tests": significance,
        "error_analysis": error_analysis,
        "latex_table": _format_latex_table(
            summary,
            eval_run_mode=eval_run_mode,
            significance=significance,
            table_label=table_label,
            metrics_profile=metrics_profile,
        ),
        "details": detail_rows,
    }
    if metrics_profile == "v4":
        layer_summary = summarize_v4_layers(detail_rows, modes=modes)
        report["summary_v4_layers"] = layer_summary
        report["latex_table_v4_layers"] = format_latex_v4_tables(
            layer_summary,
            eval_run_mode=eval_run_mode.value,
        )
        report["latex_table"] = report["latex_table_v4_layers"]
    if snapshot_date:
        report["snapshot_date"] = snapshot_date
    report["gold_file"] = str(gold_path)
    if gold_path.is_file():
        report["gold_sha256"] = _file_sha256(gold_path)
    if gold_source:
        report["gold_source_filter"] = gold_source
    if kg_snapshot:
        report["kg_snapshot"] = kg_snapshot
    report["run_started_at"] = datetime.now(timezone.utc).isoformat()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="D-01 hybrid quality ablation (4 Graph-RAG configs)"
    )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument(
        "--intents",
        type=str,
        default=None,
        help="Comma-separated intents filter: pathfinding,course_rec,competency_relation",
    )
    parser.add_argument(
        "--modes",
        type=str,
        default=None,
        help="Comma-separated fusion modes: vector_only,graph_only,late_fusion,tight_fusion",
    )
    parser.add_argument(
        "--eval-mode",
        type=str,
        default="static",
        choices=["static", "generative"],
        help="static=formatter baseline; generative=LLM + cosine similarity",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--sample-strategy",
        type=str,
        default=None,
        choices=["stratified"],
        help="stratified: proportional sample instead of --limit head slice",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Target N cases when --sample-strategy stratified",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for stratified sample")
    parser.add_argument(
        "--sample-by",
        type=str,
        default="intent,career",
        help="Comma-separated stratification fields (default: intent,career)",
    )
    parser.add_argument(
        "--qdrant-collection",
        type=str,
        default=None,
        help="Override QDRANT_COLLECTION for this run (e.g. career_roadmap_pre_cr)",
    )
    parser.add_argument(
        "--bootstrap-gold",
        action="store_true",
        help="Fill missing gold_skills/gold_course_codes from Neo4j at runtime",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--latex-out", type=Path, default=None)
    parser.add_argument(
        "--metrics-profile",
        type=str,
        default="v4",
        choices=["v1", "v2", "v3", "v4"],
        help=(
            "v4 (default): 3-layer fusion comparison; v3: legacy single-table metrics"
        ),
    )
    parser.add_argument(
        "--snapshot-date",
        type=str,
        default=None,
        help="Reproducibility tag stored in JSON (e.g. 2026-06-12)",
    )
    parser.add_argument(
        "--gold-source",
        type=str,
        default=None,
        choices=["all", "derived", "independent"],
        help="Filter cases by gold_source metadata",
    )
    parser.add_argument(
        "--dual-gold-compare",
        action="store_true",
        help="Run ablation on derived + independent gold and emit comparison block",
    )
    parser.add_argument(
        "--derived-gold",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval" / "answer_gold_v2.jsonl",
        help="Derived gold file for --dual-gold-compare",
    )
    parser.add_argument(
        "--independent-gold",
        type=Path,
        default=PROJECT_ROOT / "data" / "eval" / "answer_gold_independent.jsonl",
        help="Independent gold file for --dual-gold-compare",
    )
    parser.add_argument(
        "--kg-snapshot",
        type=str,
        default=None,
        help="D-07 B2c snapshot tag (e.g. kg_v0_pre_enrich, kg_v1_post_enrich)",
    )
    parser.add_argument(
        "--stratified-csv-out",
        type=Path,
        default=None,
        help="D-06 export grouped metrics CSV for thesis charts",
    )
    args = parser.parse_args()

    if args.qdrant_collection:
        import os

        os.environ["QDRANT_COLLECTION"] = args.qdrant_collection
        from app.core import config as _config

        _config.settings = _config.Settings()

    fusion_modes = _parse_fusion_modes(args.modes)
    eval_mode = _parse_eval_mode(args.eval_mode)
    intent_filter = (
        {x.strip() for x in args.intents.split(",") if x.strip()}
        if args.intents
        else None
    )
    report = run_ablation(
        gold_path=args.gold,
        modes=fusion_modes,
        limit=args.limit,
        bootstrap_gold=args.bootstrap_gold,
        eval_run_mode=eval_mode,
        metrics_profile=args.metrics_profile,
        snapshot_date=args.snapshot_date,
        intents=intent_filter,
        sample_strategy=args.sample_strategy,
        sample_size=args.sample_size,
        sample_seed=args.seed,
        sample_by=tuple(
            f.strip() for f in (args.sample_by or "intent,career").split(",") if f.strip()
        ),
        gold_source=args.gold_source,
        kg_snapshot=args.kg_snapshot,
    )

    if args.dual_gold_compare:
        derived_report = run_ablation(
            gold_path=args.derived_gold,
            modes=fusion_modes,
            limit=args.limit,
            bootstrap_gold=False,
            eval_run_mode=eval_mode,
            metrics_profile=args.metrics_profile,
            snapshot_date=args.snapshot_date,
            intents=intent_filter,
            sample_strategy=args.sample_strategy,
            sample_size=args.sample_size,
            sample_seed=args.seed,
            sample_by=tuple(
                f.strip() for f in (args.sample_by or "intent,career").split(",") if f.strip()
            ),
            gold_source="derived",
        )
        indep_report = run_ablation(
            gold_path=args.independent_gold,
            modes=fusion_modes,
            limit=args.limit,
            bootstrap_gold=False,
            eval_run_mode=eval_mode,
            metrics_profile=args.metrics_profile,
            snapshot_date=args.snapshot_date,
            intents=intent_filter,
            sample_strategy=args.sample_strategy,
            sample_size=args.sample_size,
            sample_seed=args.seed,
            sample_by=tuple(
                f.strip() for f in (args.sample_by or "intent,career").split(",") if f.strip()
            ),
            gold_source="independent",
        )
        primary_metric = (
            D01_PRIMARY_METRIC if args.metrics_profile in ("v2", "v3") else "faithfulness"
        )
        report["dual_gold_comparison"] = _dual_gold_comparison_row(
            derived_report,
            indep_report,
            metric=primary_metric,
        )
        report["dual_gold_reports"] = {
            "derived": derived_report["summary"],
            "independent": indep_report["summary"],
        }

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if report.get("significance_tests"):
        print("\n--- Significance tests ---\n")
        print(json.dumps(report["significance_tests"], ensure_ascii=False, indent=2))
    _safe_print("\n--- LaTeX table ---\n")
    _safe_print(report["latex_table"])

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON report: {args.json_out}")

    if args.latex_out:
        args.latex_out.parent.mkdir(parents=True, exist_ok=True)
        args.latex_out.write_text(report["latex_table"], encoding="utf-8")
        print(f"LaTeX table: {args.latex_out}")

    if args.stratified_csv_out:
        metric = (
            D01_PRIMARY_METRIC if args.metrics_profile in ("v2", "v3") else "faithfulness"
        )
        export_stratified_breakdown_csv(
            report.get("details") or [],
            args.stratified_csv_out,
            metric=metric,
        )
        print(f"Stratified CSV: {args.stratified_csv_out}")


if __name__ == "__main__":
    main()
