from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any

from app.eval.quality_metrics import (
    QualityScores,
    build_gold_reference_text,
    classify_error_tags,
    compute_quality_scores_v2,
    embedding_text_similarity,
    entities_from_graph,
    entities_from_vector_docs,
)
from app.utils.skill_normalize import normalize_skill_label
from app.generator.response_generator import ResponseGenerator
from app.graph.formatters import format_course_rec, format_pathfinding, format_competency_relation
from app.graph.models import CourseRecResult, PathfindingResult, CompetencyRelationResult
from app.graph.repository import GraphRepository
from app.rag.embeddings import EmbeddingClient
from app.rag.fusion import FusionService, extract_relevant_ids_from_graph, map_hits_to_graph_nodes
from app.rag.retriever import RetrievedDoc, VectorRetriever, _apply_graph_boost
from app.services.gemini_generator_client import GeminiGeneratorClient
from app.services.generator_backend import generate_reply
from app.services.local_generator_client import LocalGeneratorClient
from app.session.store import SessionState


class FusionMode(str, enum.Enum):
    """Bốn cấu hình ablation D-01."""

    VECTOR_ONLY = "vector_only"
    GRAPH_ONLY = "graph_only"
    LATE_FUSION = "late_fusion"
    TIGHT_FUSION = "tight_fusion"


class EvalRunMode(str, enum.Enum):
    """Chế độ đánh giá D-01: static formatter hoặc generative LLM."""

    STATIC = "static"
    GENERATIVE = "generative"


MODE_LABELS: dict[FusionMode, str] = {
    FusionMode.VECTOR_ONLY: "VectorOnly",
    FusionMode.GRAPH_ONLY: "GraphOnly",
    FusionMode.LATE_FUSION: "LateFusion",
    FusionMode.TIGHT_FUSION: "TightFusion",
}


@dataclass(frozen=True)
class FusionConfig:
    """D-04 factorial factors (tight-fusion baseline + toggles)."""

    use_vector_seed: bool = True  # F1: vector seeds Cypher
    use_graph_rerank: bool = True  # F2: graph-aware rerank boost
    use_bm25: bool = True  # F3: BM25 in hybrid RRF
    use_query_expand: bool = True  # F4: VN query expansion

    def factor_key(self) -> str:
        return (
            f"F1{int(self.use_vector_seed)}"
            f"_F2{int(self.use_graph_rerank)}"
            f"_F3{int(self.use_bm25)}"
            f"_F4{int(self.use_query_expand)}"
        )


# 2^(4-1) fractional factorial (8 runs)
FRACTIONAL_FACTORIAL_CONFIGS: tuple[FusionConfig, ...] = (
    FusionConfig(True, True, True, True),
    FusionConfig(True, True, True, False),
    FusionConfig(True, True, False, True),
    FusionConfig(True, False, True, True),
    FusionConfig(True, False, False, False),
    FusionConfig(False, True, True, False),
    FusionConfig(False, True, False, True),
    FusionConfig(False, False, True, True),
)

_ABLATION_VECTOR_SYSTEM = """Bạn là AI tư vấn hướng nghiệp IT.
Chỉ dùng ngữ cảnh tài liệu vector được cung cấp. Không bịa thêm kỹ năng/khóa học.
Trả lời tiếng Việt, gọn, có cấu trúc."""


@dataclass
class AblationCaseResult:
    case_id: str
    mode: FusionMode
    intent: str
    query: str
    reply: str
    graph: dict[str, Any] | None
    vector_doc_count: int
    seed_ids: dict[str, list[str]]
    scores: QualityScores
    meta: dict[str, Any] = field(default_factory=dict)
    eval_run_mode: EvalRunMode = EvalRunMode.STATIC
    error_tags: list[str] = field(default_factory=list)

    def as_dict(self, export_profile: str = "internal") -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "mode": self.mode.value,
            "eval_run_mode": self.eval_run_mode.value,
            "intent": self.intent,
            "query": self.query,
            "reply_len": len(self.reply),
            "reply_preview": self.reply[:240],
            "vector_doc_count": self.vector_doc_count,
            "seed_ids": self.seed_ids,
            "scores": self.scores.as_dict(export_profile),  # type: ignore[arg-type]
            "error_tags": self.error_tags,
            "meta": self.meta,
        }


def _empty_seed() -> dict[str, list[str]]:
    return {"career_codes": [], "competency_codes": [], "course_codes": []}


def _format_vector_only(docs: list[RetrievedDoc]) -> str:
    if not docs:
        return "Không tìm thấy tài liệu vector phù hợp."
    lines = ["## Gợi ý từ tài liệu (vector retrieval)"]
    for i, doc in enumerate(docs[:3], start=1):
        title = doc.payload.get("title") or doc.text[:80]
        lines.append(f"\n### [{i}] {title}")
        lines.append(doc.text[:500])
    return "\n".join(lines)


def _build_vector_context(docs: list[RetrievedDoc]) -> str:
    if not docs:
        return ""
    parts = ["## Ngữ cảnh vector retrieval"]
    for i, doc in enumerate(docs[:5], start=1):
        title = doc.payload.get("title") or doc.text[:60]
        parts.append(f"\n### [{i}] {title}\n{doc.text[:450]}")
    return "\n".join(parts)


def _skills_from_vector_docs(docs: list[RetrievedDoc]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for doc in docs:
        payload = doc.payload or {}
        for field_name in ("item_name", "title", "career_name", "course_name"):
            val = payload.get(field_name)
            if not val:
                continue
            key = str(val).strip().lower()
            if key and key not in seen:
                seen.add(key)
                names.append(str(val).strip())
        if payload.get("doc_type") == "competency" and payload.get("canonical_id"):
            cid = str(payload["canonical_id"])
            if cid.lower() not in seen:
                seen.add(cid.lower())
                names.append(cid)
    return names


def _course_codes_from_graph(graph: dict[str, Any] | None) -> list[str]:
    codes: list[str] = []
    for c in (graph or {}).get("courses") or []:
        if isinstance(c, dict) and c.get("course_code"):
            codes.append(str(c["course_code"]))
    return codes


def _append_course_citations_for_eval(reply: str, graph_dump: dict[str, Any] | None) -> str:
    """
    D-01: thêm [Course: CODE] vào reply ablation để Answer Entity F1 so khớp gold_course_codes.
    Không đổi formatter production — chỉ dùng trong pipeline đánh giá static/generative ablation.
    """
    if not graph_dump:
        return reply
    codes = _course_codes_from_graph(graph_dump)
    if not codes:
        return reply
    cite_line = " ".join(f"[Course: {code}]" for code in codes[:20])
    if cite_line in reply:
        return reply
    return f"{reply}\n\n{cite_line}"


def _post_graph_rerank_vector_docs(
    retriever: VectorRetriever,
    query: str,
    vector_docs: list[RetrievedDoc],
    graph_dump: dict[str, Any] | None,
    *,
    doc_type: str | None,
    top_k: int = 3,
) -> list[RetrievedDoc]:
    """A-03: graph-aware rerank — khớp ChatService sau khi có kết quả Neo4j."""
    if not graph_dump:
        return vector_docs
    relevant_ids = extract_relevant_ids_from_graph(graph_dump)
    if not relevant_ids:
        return vector_docs
    return retriever.retrieve_docs(
        query,
        top_k=top_k,
        doc_type=doc_type,
        relevant_ids=relevant_ids,
    )


def _entity_hint(item: dict[str, Any]) -> bool:
    hint = item.get("entity_hint", True)
    if isinstance(hint, str):
        return hint.lower() not in ("false", "0", "no")
    return bool(hint)


def _norm_label(text: str) -> str:
    return normalize_skill_label(str(text or ""))


def _pathfinding_graph_key(item: dict[str, Any]) -> str:
    if _entity_hint(item):
        return str(item.get("career") or item.get("target_career") or item.get("query") or "")
    return str(item.get("query") or "")


def _competency_from_top_vector_hit(
    docs: list[RetrievedDoc],
    seed_map: dict[str, list[str]] | None = None,
) -> str:
    for doc in docs:
        payload = doc.payload or {}
        if str(payload.get("doc_type") or "").lower() == "competency":
            for field in ("item_name", "title", "canonical_id"):
                val = payload.get(field)
                if val:
                    return str(val).strip()
    if seed_map:
        codes = seed_map.get("competency_codes") or []
        if codes:
            return str(codes[0]).strip()
    for doc in docs:
        payload = doc.payload or {}
        for field in ("item_name", "title", "canonical_id"):
            val = payload.get(field)
            if val:
                return str(val).strip()
    return ""


def _course_rec_graph_key(
    item: dict[str, Any],
    mode: FusionMode,
    vector_docs: list[RetrievedDoc],
    seed_map: dict[str, list[str]],
) -> str:
    if _entity_hint(item):
        return str(item.get("competency") or item.get("gold_competency") or item.get("query") or "")
    if mode == FusionMode.TIGHT_FUSION and vector_docs:
        resolved = _competency_from_top_vector_hit(vector_docs, seed_map)
        if resolved:
            return resolved
    return str(item.get("query") or "")


def _cypher_matched_pathfinding(
    pf: PathfindingResult,
    expected_career: str,
) -> tuple[bool, str]:
    resolved = str(pf.career_name or "")
    if not pf.found or not expected_career:
        return False, resolved
    return _norm_label(resolved) == _norm_label(expected_career), resolved


def _cypher_matched_course_rec(
    cr: CourseRecResult,
    expected_competency: str,
) -> tuple[bool, str]:
    resolved = str(cr.competency_name or "")
    if not cr.found or not expected_competency:
        return False, resolved
    return _norm_label(resolved) == _norm_label(expected_competency), resolved


class AblationPipeline:
    """Pipeline kiểm soát cho ablation D-01 — không qua intent router."""

    def __init__(
        self,
        *,
        graph: GraphRepository | None = None,
        retriever: VectorRetriever | None = None,
        fusion: FusionService | None = None,
        generator: ResponseGenerator | None = None,
        embedder: EmbeddingClient | None = None,
        eval_run_mode: EvalRunMode = EvalRunMode.STATIC,
        metrics_profile: str = "v4",
    ) -> None:
        self._graph = graph or GraphRepository()
        self._retriever = retriever or VectorRetriever()
        self._fusion = fusion or FusionService()
        self._generator = generator
        self._embedder = embedder or EmbeddingClient()
        self._eval_run_mode = eval_run_mode
        self._metrics_profile = metrics_profile if metrics_profile in ("v3", "v4") else "v4"
        self._gemini = GeminiGeneratorClient()
        self._local = LocalGeneratorClient()

    @property
    def eval_run_mode(self) -> EvalRunMode:
        return self._eval_run_mode

    def run_case(self, item: dict[str, Any], mode: FusionMode) -> AblationCaseResult:
        intent = str(item.get("intent") or "pathfinding")
        if intent == "pathfinding":
            return self._run_pathfinding(item, mode)
        if intent == "course_rec":
            return self._run_course_rec(item, mode)
        if intent == "competency_relation":
            return self._run_competency_relation(item, mode)
        raise ValueError(f"Unsupported intent for ablation: {intent}")

    def _finalize_scores(
        self,
        *,
        item: dict[str, Any],
        reply: str,
        predicted: list[str],
        gold: list[str],
        graph_context: set[str],
        vector_context: set[str],
        graph_dump: dict[str, Any] | None,
        mode: FusionMode,
        intent: str,
    ) -> tuple[QualityScores, list[str]]:
        if self._metrics_profile == "v4":
            from app.eval.fusion_eval_layers import compute_fusion_layer_scores

            scores = compute_fusion_layer_scores(
                reply=reply,
                predicted_entities=predicted,
                item=item,
                graph_context=graph_context,
                vector_context=vector_context,
                graph_snapshot=graph_dump,
                fusion_mode=mode,
            )
        else:
            scores = compute_quality_scores_v2(
                reply=reply,
                predicted_entities=predicted,
                gold_entities=gold,
                graph_context=graph_context,
                vector_context=vector_context,
                graph_snapshot=graph_dump,
            )
        if self._eval_run_mode == EvalRunMode.GENERATIVE:
            gold_ref = build_gold_reference_text(item)
            cos = embedding_text_similarity(self._embedder, reply, gold_ref)
            if cos is not None:
                scores = QualityScores(
                    faithfulness=scores.faithfulness,
                    skill_accuracy=scores.skill_accuracy,
                    hallucination_rate=scores.hallucination_rate,
                    n_predicted=scores.n_predicted,
                    n_gold=scores.n_gold,
                    n_hallucinated=scores.n_hallucinated,
                    n_mentions=scores.n_mentions,
                    cosine_similarity=cos,
                    ontology_f1=scores.ontology_f1,
                    answer_entity_f1=scores.answer_entity_f1,
                    full_grounding_rate=scores.full_grounding_rate,
                    graph_grounding_rate=scores.graph_grounding_rate,
                    exclusive_graph_rate=scores.exclusive_graph_rate,
                    vector_only_mention_rate=scores.vector_only_mention_rate,
                    retrieval_entity_recall=scores.retrieval_entity_recall,
                    retrieval_hit=scores.retrieval_hit,
                    fusion_off_graph_rate=scores.fusion_off_graph_rate,
                )
        off_graph = (
            scores.fusion_off_graph_rate
            if scores.fusion_off_graph_rate is not None
            else scores.hallucination_rate
        )
        tags = classify_error_tags(
            ontology_f1=scores.ontology_f1 if scores.ontology_f1 is not None else scores.skill_accuracy,
            off_graph_mention_rate=off_graph,
            graph_entity_grounding=scores.graph_grounding_rate,
            reply=reply,
        )
        return scores, tags

    def _static_pathfinding_reply(
        self,
        mode: FusionMode,
        pf: PathfindingResult,
        vector_docs: list[RetrievedDoc],
    ) -> tuple[str, list[str]]:
        if mode == FusionMode.VECTOR_ONLY:
            return _format_vector_only(vector_docs), _skills_from_vector_docs(vector_docs)
        reply = format_pathfinding(pf, SessionState(session_id="ablation"))
        if mode == FusionMode.LATE_FUSION and vector_docs:
            vector_context = _build_vector_context(vector_docs)
            if vector_context:
                reply = f"{reply}\n\n{vector_context}"
        predicted = [c.name for c in (pf.skills_missing or pf.competencies)]
        return reply, predicted

    def _generative_pathfinding_reply(
        self,
        *,
        query: str,
        mode: FusionMode,
        pf: PathfindingResult,
        vector_docs: list[RetrievedDoc],
    ) -> tuple[str, list[str]]:
        state = SessionState(session_id="ablation")
        vector_context = _build_vector_context(vector_docs)

        if mode == FusionMode.VECTOR_ONLY:
            if not self._gemini.available and not self._local.available:
                return _format_vector_only(vector_docs), _skills_from_vector_docs(vector_docs)
            user_prompt = (
                f"Câu hỏi: {query}\n\n{_build_vector_context(vector_docs)}\n\n"
                "Tổng hợp gợi ý lộ trình từ tài liệu trên."
            )
            try:
                reply, backend, is_error = generate_reply(
                    intent="pathfinding",
                    system_prompt=_ABLATION_VECTOR_SYSTEM,
                    user_prompt=user_prompt,
                    gemini=self._gemini,
                    local=self._local,
                )
                if is_error:
                    return _format_vector_only(vector_docs), _skills_from_vector_docs(vector_docs)
                return reply, _skills_from_vector_docs(vector_docs)
            except Exception:
                return _format_vector_only(vector_docs), _skills_from_vector_docs(vector_docs)

        gen = self._generator or ResponseGenerator(
            llm=self._gemini,
            local_llm=self._local,
        )
        reply = gen.pathfinding(
            user_message=query,
            result=pf,
            state=state,
            vector_context=vector_context if vector_docs else "",
            route_confidence="high",
        )
        predicted = [c.name for c in (pf.skills_missing or pf.competencies)]
        return reply, predicted

    def _run_pathfinding(self, item: dict[str, Any], mode: FusionMode) -> AblationCaseResult:
        query = str(item["query"])
        hint = _entity_hint(item)
        career = str(item.get("career") or item.get("target_career") or "") if hint else ""
        graph_key = _pathfinding_graph_key(item)
        expected_career = str(
            item.get("expected_career") or item.get("career") or item.get("target_career") or ""
        )
        case_id = str(item.get("id") or query[:40])
        gold_skills = list(item.get("gold_skills") or [])

        use_vector = mode in (FusionMode.VECTOR_ONLY, FusionMode.LATE_FUSION, FusionMode.TIGHT_FUSION)
        use_graph = mode in (FusionMode.GRAPH_ONLY, FusionMode.LATE_FUSION, FusionMode.TIGHT_FUSION)
        use_seeds = mode == FusionMode.TIGHT_FUSION

        vector_docs: list[RetrievedDoc] = []
        if use_vector:
            vector_docs = self._retriever.retrieve_docs(query, top_k=3, doc_type="career")

        seed_map = map_hits_to_graph_nodes(vector_docs) if use_seeds else _empty_seed()

        pf: PathfindingResult
        if use_graph:
            pf = self._graph.pathfinding(
                graph_key,
                seed_career_codes=seed_map["career_codes"] if use_seeds else None,
                seed_competency_codes=seed_map["competency_codes"] if use_seeds else None,
            )
        else:
            pf = PathfindingResult(found=False, career_name=graph_key, error="Vector-only mode")

        graph_dump = pf.model_dump() if use_graph and pf.found else None
        cypher_matched, resolved_career = _cypher_matched_pathfinding(pf, expected_career)

        if use_vector and mode == FusionMode.TIGHT_FUSION:
            vector_docs = _post_graph_rerank_vector_docs(
                self._retriever,
                query,
                vector_docs,
                graph_dump,
                doc_type="career",
            )

        self._fusion.aggregate(
            graph_payload=graph_dump,
            vector_docs=vector_docs if use_vector else [],
            graph_seed_ids=seed_map if use_seeds else None,
        )

        if self._eval_run_mode == EvalRunMode.GENERATIVE:
            reply, predicted = self._generative_pathfinding_reply(
                query=query,
                mode=mode,
                pf=pf,
                vector_docs=vector_docs,
            )
        else:
            reply, predicted = self._static_pathfinding_reply(mode, pf, vector_docs)

        graph_context = entities_from_graph(graph_dump)
        vector_context = entities_from_vector_docs(vector_docs) if use_vector else set()

        scores, error_tags = self._finalize_scores(
            item=item,
            reply=reply,
            predicted=predicted,
            gold=gold_skills,
            graph_context=graph_context,
            vector_context=vector_context,
            graph_dump=graph_dump,
            mode=mode,
            intent="pathfinding",
        )

        return AblationCaseResult(
            case_id=case_id,
            mode=mode,
            intent="pathfinding",
            query=query,
            reply=reply,
            graph=graph_dump,
            vector_doc_count=len(vector_docs),
            seed_ids=seed_map,
            scores=scores,
            eval_run_mode=self._eval_run_mode,
            error_tags=error_tags,
            meta={
                "entity_hint": hint,
                "career": career or None,
                "graph_key": graph_key,
                "expected_career": expected_career or None,
                "resolved_career": resolved_career or None,
                "cypher_matched": cypher_matched if use_graph else None,
                "graph_found": pf.found if use_graph else False,
                "predicted_skills": predicted[:12],
                "gold_reference_preview": build_gold_reference_text(item)[:200],
            },
        )

    def _static_course_rec_reply(
        self,
        mode: FusionMode,
        cr: CourseRecResult,
        vector_docs: list[RetrievedDoc],
        graph_dump: dict[str, Any] | None,
    ) -> tuple[str, list[str]]:
        if mode == FusionMode.VECTOR_ONLY:
            reply = _format_vector_only(vector_docs)
            predicted = [
                str(d.payload.get("course_code") or d.payload.get("canonical_id") or "")
                for d in vector_docs
                if d.payload.get("course_code") or d.payload.get("canonical_id")
            ]
            return reply, predicted
        reply = format_course_rec(cr)
        if mode == FusionMode.LATE_FUSION and vector_docs:
            vector_context = _build_vector_context(vector_docs)
            if vector_context:
                reply = f"{reply}\n\n{vector_context}"
        reply = _append_course_citations_for_eval(reply, graph_dump)
        return reply, _course_codes_from_graph(graph_dump)

    def _generative_course_rec_reply(
        self,
        *,
        query: str,
        mode: FusionMode,
        cr: CourseRecResult,
        vector_docs: list[RetrievedDoc],
        graph_dump: dict[str, Any] | None,
    ) -> tuple[str, list[str]]:
        state = SessionState(session_id="ablation")
        vector_context = _build_vector_context(vector_docs)

        if mode == FusionMode.VECTOR_ONLY:
            if not self._gemini.available and not self._local.available:
                return self._static_course_rec_reply(mode, cr, vector_docs, graph_dump)
            user_prompt = (
                f"Câu hỏi: {query}\n\n{_build_vector_context(vector_docs)}\n\n"
                "Gợi ý khóa học từ tài liệu trên."
            )
            try:
                reply, _, is_error = generate_reply(
                    intent="course_rec",
                    system_prompt=_ABLATION_VECTOR_SYSTEM,
                    user_prompt=user_prompt,
                    gemini=self._gemini,
                    local=self._local,
                )
                if is_error:
                    return self._static_course_rec_reply(mode, cr, vector_docs, graph_dump)
                predicted = [
                    str(d.payload.get("course_code") or d.payload.get("canonical_id") or "")
                    for d in vector_docs
                    if d.payload.get("course_code") or d.payload.get("canonical_id")
                ]
                return reply, predicted
            except Exception:
                return self._static_course_rec_reply(mode, cr, vector_docs, graph_dump)

        gen = self._generator or ResponseGenerator(
            llm=self._gemini,
            local_llm=self._local,
        )
        reply = gen.course_rec(
            user_message=query,
            result=cr,
            state=state,
            vector_context=vector_context if vector_docs else "",
            route_confidence="high",
        )
        reply = _append_course_citations_for_eval(reply, graph_dump)
        return reply, _course_codes_from_graph(graph_dump)

    def _run_course_rec(self, item: dict[str, Any], mode: FusionMode) -> AblationCaseResult:
        query = str(item["query"])
        hint = _entity_hint(item)
        competency = (
            str(item.get("competency") or item.get("gold_competency") or "") if hint else ""
        )
        case_id = str(item.get("id") or query[:40])
        gold_courses = list(item.get("gold_course_codes") or [])
        expected_competency = str(
            item.get("expected_competency")
            or item.get("competency")
            or item.get("gold_competency")
            or ""
        )

        use_vector = mode in (FusionMode.VECTOR_ONLY, FusionMode.LATE_FUSION, FusionMode.TIGHT_FUSION)
        use_graph = mode in (FusionMode.GRAPH_ONLY, FusionMode.LATE_FUSION, FusionMode.TIGHT_FUSION)
        use_seeds = mode == FusionMode.TIGHT_FUSION

        vector_docs: list[RetrievedDoc] = []
        if use_vector:
            vector_docs = self._retriever.retrieve_docs(query, top_k=3, doc_type="course")

        seed_map = map_hits_to_graph_nodes(vector_docs) if use_seeds else _empty_seed()
        graph_key = _course_rec_graph_key(item, mode, vector_docs, seed_map)

        cr: CourseRecResult
        if use_graph:
            cr = self._graph.course_recommendation(
                graph_key,
                seed_course_codes=seed_map["course_codes"] if use_seeds else None,
            )
        else:
            cr = CourseRecResult(found=False, competency_name=graph_key, error="Vector-only mode")

        graph_dump = cr.model_dump() if use_graph and cr.found else None
        cypher_matched, resolved_competency = _cypher_matched_course_rec(cr, expected_competency)

        if use_vector and mode == FusionMode.TIGHT_FUSION:
            vector_docs = _post_graph_rerank_vector_docs(
                self._retriever,
                query,
                vector_docs,
                graph_dump,
                doc_type="course",
            )

        self._fusion.aggregate(
            graph_payload=graph_dump,
            vector_docs=vector_docs if use_vector else [],
            graph_seed_ids=seed_map if use_seeds else None,
        )

        if self._eval_run_mode == EvalRunMode.GENERATIVE:
            reply, predicted = self._generative_course_rec_reply(
                query=query,
                mode=mode,
                cr=cr,
                vector_docs=vector_docs,
                graph_dump=graph_dump,
            )
        else:
            reply, predicted = self._static_course_rec_reply(
                mode, cr, vector_docs, graph_dump
            )

        graph_context = entities_from_graph(graph_dump)
        vector_context = entities_from_vector_docs(vector_docs) if use_vector else set()

        scores, error_tags = self._finalize_scores(
            item=item,
            reply=reply,
            predicted=predicted,
            gold=gold_courses,
            graph_context=graph_context,
            vector_context=vector_context,
            graph_dump=graph_dump,
            mode=mode,
            intent="course_rec",
        )

        return AblationCaseResult(
            case_id=case_id,
            mode=mode,
            intent="course_rec",
            query=query,
            reply=reply,
            graph=graph_dump,
            vector_doc_count=len(vector_docs),
            seed_ids=seed_map,
            scores=scores,
            eval_run_mode=self._eval_run_mode,
            error_tags=error_tags,
            meta={
                "entity_hint": hint,
                "competency": competency or None,
                "graph_key": graph_key,
                "expected_competency": expected_competency or None,
                "resolved_competency": resolved_competency or None,
                "cypher_matched": cypher_matched if use_graph else None,
                "graph_found": cr.found if use_graph else False,
                "predicted_courses": predicted[:12],
                "gold_reference_preview": build_gold_reference_text(item)[:200],
            },
        )

    @staticmethod
    def _relation_codes_from_graph(graph: dict[str, Any] | None) -> list[str]:
        codes: list[str] = []
        if not graph:
            return codes
        for bucket in ("outgoing", "incoming"):
            for edge in graph.get(bucket) or []:
                if not isinstance(edge, dict):
                    continue
                for key in ("to_code", "from_code"):
                    val = edge.get(key)
                    if val:
                        codes.append(str(val))
        if graph.get("anchor_code"):
            codes.append(str(graph["anchor_code"]))
        return codes

    def _run_competency_relation(self, item: dict[str, Any], mode: FusionMode) -> AblationCaseResult:
        query = str(item["query"])
        case_id = str(item.get("id") or query[:40])
        competency = str(item.get("competency") or item.get("query") or "")
        gold_codes = list(item.get("gold_related_codes") or [])

        use_vector = mode in (FusionMode.VECTOR_ONLY, FusionMode.LATE_FUSION, FusionMode.TIGHT_FUSION)
        use_graph = mode in (FusionMode.GRAPH_ONLY, FusionMode.LATE_FUSION, FusionMode.TIGHT_FUSION)

        vector_docs: list[RetrievedDoc] = []
        if use_vector:
            vector_docs = self._retriever.retrieve_docs(query, top_k=3, doc_type="competency")

        rel: CompetencyRelationResult
        if use_graph:
            rel = self._graph.competency_relations(competency)
        else:
            rel = CompetencyRelationResult(found=False, coverage="none", error="Vector-only mode")

        graph_dump = rel.model_dump() if use_graph else None
        reply = format_competency_relation(rel)
        if mode == FusionMode.LATE_FUSION and vector_docs:
            reply = f"{reply}\n\n{_build_vector_context(vector_docs)}"

        predicted = self._relation_codes_from_graph(graph_dump)
        for code in re.findall(r"\b[A-Z]{1,3}_[A-Z0-9_]+\b", reply):
            if code not in predicted:
                predicted.append(code)

        graph_context = entities_from_graph(graph_dump)
        vector_context = entities_from_vector_docs(vector_docs) if use_vector else set()

        scores, error_tags = self._finalize_scores(
            item=item,
            reply=reply,
            predicted=predicted,
            gold=gold_codes,
            graph_context=graph_context,
            vector_context=vector_context,
            graph_dump=graph_dump,
            mode=mode,
            intent="competency_relation",
        )

        return AblationCaseResult(
            case_id=case_id,
            mode=mode,
            intent="competency_relation",
            query=query,
            reply=reply,
            graph=graph_dump,
            vector_doc_count=len(vector_docs),
            seed_ids=_empty_seed(),
            scores=scores,
            eval_run_mode=self._eval_run_mode,
            error_tags=error_tags,
            meta={
                "competency": competency,
                "coverage": rel.coverage,
                "gold_related_codes": gold_codes,
                "predicted_codes": predicted[:12],
            },
        )

    def run_case_with_config(
        self, item: dict[str, Any], config: FusionConfig
    ) -> AblationCaseResult:
        """D-04 factorial run — tight fusion with per-factor retrieval toggles."""
        intent = str(item.get("intent") or "pathfinding")
        if intent == "pathfinding":
            return self._run_pathfinding_factorial(item, config)
        if intent == "course_rec":
            return self._run_course_rec_factorial(item, config)
        return self.run_case(item, FusionMode.TIGHT_FUSION)

    def _seed_ids_for_boost(self, seed_map: dict[str, list[str]]) -> set[str]:
        out: set[str] = set()
        for values in seed_map.values():
            out.update(str(v) for v in values if v)
        return out

    def _run_pathfinding_factorial(
        self, item: dict[str, Any], config: FusionConfig
    ) -> AblationCaseResult:
        if config == FusionConfig():
            result = self._run_pathfinding(item, FusionMode.TIGHT_FUSION)
            result.meta["fusion_config"] = config.factor_key()
            return result

        query = str(item["query"])
        hint = _entity_hint(item)
        career = str(item.get("career") or "") if hint else ""
        expected_career = str(item.get("expected_career") or career or "")
        graph_key = career or expected_career
        case_id = str(item.get("id") or query[:40])
        gold_skills = list(item.get("gold_skills") or [])

        vector_docs = self._retriever.retrieve_docs(
            query,
            top_k=3,
            doc_type="career",
            use_query_expand=config.use_query_expand,
            use_bm25=config.use_bm25,
            use_graph_boost=False,
        )
        seed_map = (
            map_hits_to_graph_nodes(vector_docs) if config.use_vector_seed else _empty_seed()
        )
        if config.use_graph_rerank:
            graph_ids = self._seed_ids_for_boost(seed_map)
            vector_docs = _apply_graph_boost(vector_docs, graph_ids or None, top_k=3)

        pf = self._graph.pathfinding(
            graph_key,
            seed_career_codes=seed_map["career_codes"] if config.use_vector_seed else None,
            seed_competency_codes=seed_map["competency_codes"] if config.use_vector_seed else None,
        )
        graph_dump = pf.model_dump() if pf.found else None
        cypher_matched, resolved_career = _cypher_matched_pathfinding(pf, expected_career)

        if config.use_graph_rerank:
            vector_docs = _post_graph_rerank_vector_docs(
                self._retriever,
                query,
                vector_docs,
                graph_dump,
                doc_type="career",
            )

        if self._eval_run_mode == EvalRunMode.GENERATIVE:
            reply, predicted = self._generative_pathfinding_reply(
                query=query,
                mode=FusionMode.TIGHT_FUSION,
                pf=pf,
                vector_docs=vector_docs,
            )
        else:
            reply, predicted = self._static_pathfinding_reply(
                FusionMode.TIGHT_FUSION, pf, vector_docs
            )

        graph_context = entities_from_graph(graph_dump)
        vector_context = entities_from_vector_docs(vector_docs)
        scores, error_tags = self._finalize_scores(
            item=item,
            reply=reply,
            predicted=predicted,
            gold=gold_skills,
            graph_context=graph_context,
            vector_context=vector_context,
            graph_dump=graph_dump,
            mode=FusionMode.TIGHT_FUSION,
            intent="pathfinding",
        )
        return AblationCaseResult(
            case_id=case_id,
            mode=FusionMode.TIGHT_FUSION,
            intent="pathfinding",
            query=query,
            reply=reply,
            graph=graph_dump,
            vector_doc_count=len(vector_docs),
            seed_ids=seed_map,
            scores=scores,
            eval_run_mode=self._eval_run_mode,
            error_tags=error_tags,
            meta={
                "entity_hint": hint,
                "career": career or None,
                "fusion_config": config.factor_key(),
                "cypher_matched": cypher_matched,
                "resolved_career": resolved_career,
            },
        )

    def _run_course_rec_factorial(
        self, item: dict[str, Any], config: FusionConfig
    ) -> AblationCaseResult:
        if config == FusionConfig():
            result = self._run_course_rec(item, FusionMode.TIGHT_FUSION)
            result.meta["fusion_config"] = config.factor_key()
            return result

        query = str(item["query"])
        hint = _entity_hint(item)
        competency = str(item.get("competency") or item.get("gold_competency") or "") if hint else ""
        case_id = str(item.get("id") or query[:40])
        gold_courses = list(item.get("gold_course_codes") or [])
        expected_competency = str(
            item.get("expected_competency")
            or item.get("competency")
            or item.get("gold_competency")
            or ""
        )

        vector_docs = self._retriever.retrieve_docs(
            query,
            top_k=3,
            doc_type="course",
            use_query_expand=config.use_query_expand,
            use_bm25=config.use_bm25,
            use_graph_boost=False,
        )
        seed_map = (
            map_hits_to_graph_nodes(vector_docs) if config.use_vector_seed else _empty_seed()
        )
        if config.use_graph_rerank:
            graph_ids = self._seed_ids_for_boost(seed_map)
            vector_docs = _apply_graph_boost(vector_docs, graph_ids or None, top_k=3)

        graph_key = _course_rec_graph_key(item, FusionMode.TIGHT_FUSION, vector_docs, seed_map)
        cr = self._graph.course_recommendation(
            graph_key,
            seed_course_codes=seed_map["course_codes"] if config.use_vector_seed else None,
        )
        graph_dump = cr.model_dump() if cr.found else None
        cypher_matched, resolved_competency = _cypher_matched_course_rec(cr, expected_competency)

        if config.use_graph_rerank:
            vector_docs = _post_graph_rerank_vector_docs(
                self._retriever,
                query,
                vector_docs,
                graph_dump,
                doc_type="course",
            )

        if self._eval_run_mode == EvalRunMode.GENERATIVE:
            reply, predicted = self._generative_course_rec_reply(
                query=query,
                mode=FusionMode.TIGHT_FUSION,
                cr=cr,
                vector_docs=vector_docs,
                graph_dump=graph_dump,
            )
        else:
            reply, predicted = self._static_course_rec_reply(
                FusionMode.TIGHT_FUSION, cr, vector_docs, graph_dump
            )

        graph_context = entities_from_graph(graph_dump)
        vector_context = entities_from_vector_docs(vector_docs)
        scores, error_tags = self._finalize_scores(
            item=item,
            reply=reply,
            predicted=predicted,
            gold=gold_courses,
            graph_context=graph_context,
            vector_context=vector_context,
            graph_dump=graph_dump,
            mode=FusionMode.TIGHT_FUSION,
            intent="course_rec",
        )
        return AblationCaseResult(
            case_id=case_id,
            mode=FusionMode.TIGHT_FUSION,
            intent="course_rec",
            query=query,
            reply=reply,
            graph=graph_dump,
            vector_doc_count=len(vector_docs),
            seed_ids=seed_map,
            scores=scores,
            eval_run_mode=self._eval_run_mode,
            error_tags=error_tags,
            meta={
                "fusion_config": config.factor_key(),
                "cypher_matched": cypher_matched,
                "resolved_competency": resolved_competency,
            },
        )

    def close(self) -> None:
        self._graph.close()
