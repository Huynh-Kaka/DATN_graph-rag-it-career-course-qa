from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Literal, TYPE_CHECKING

from app.generator.validator import extract_course_codes_from_snapshot
from app.utils.skill_normalize import normalize_skill_label

if TYPE_CHECKING:
    from app.rag.embeddings import EmbeddingClient

NoMentionPolicy = Literal["legacy_one", "penalize", "exclude"]
D01ExportProfile = Literal["internal", "v1", "v2", "v3", "v4"]

# D-01 v3 — tên công khai cho luận văn (tách khỏi faithfulness/hallucination của D-03 LLM judge).
D01_V3_GLOSSARY: dict[str, str] = {
    "answer_entity_f1": (
        "F1 thực thể trong câu trả lời: F1(M, G) — M = mentions trích từ reply, "
        "G = gold_entities. Đo câu trả lời hiển thị đúng/đủ so với chuẩn."
    ),
    "ontology_f1": (
        "F1 đúng/đủ ontology: F1(P, G) — P = predicted_entities từ graph/retrieval, "
        "G = gold_entities. Đo hệ thống truy xuất đúng thực thể, không phụ thuộc cách in reply."
    ),
    "graph_entity_grounding": (
        "Tỷ lệ entity trong reply có trong ngữ cảnh Neo4j (graph grounding)."
    ),
    "off_graph_mention_rate": (
        "Tỷ lệ entity trong reply không có trong graph — không phải ảo giác LLM; "
        "đo mention lệch khỏi ground-truth đồ thị."
    ),
    "vector_only_mention_rate": (
        "Tỷ lệ mention chỉ xuất hiện trong snippet vector, không có trong graph."
    ),
    "exclusive_graph_rate": (
        "Tỷ lệ mention chỉ suy ra được từ graph (vector không cung cấp)."
    ),
    "context_entity_grounding": (
        "Chỉ số phụ (diagnostic): mention bám full context graph∪vector — "
        "thường ~100% ở chế độ static formatter, không dùng làm kết luận chính."
    ),
}

_COURSE_CITE_RE = re.compile(r"\[Course:\s*([^\]]+)\]", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[\w#+.]+", re.UNICODE)


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


@dataclass
class QualityScores:
    faithfulness: float
    skill_accuracy: float
    hallucination_rate: float
    n_predicted: int = 0
    n_gold: int = 0
    n_hallucinated: int = 0
    cosine_similarity: float | None = None
    # D-01 V2 optional metrics (None = not computed or excluded from aggregate)
    ontology_f1: float | None = None
    answer_entity_f1: float | None = None
    full_grounding_rate: float | None = None
    graph_grounding_rate: float | None = None
    exclusive_graph_rate: float | None = None
    vector_only_mention_rate: float | None = None
    relation_code_recall: float | None = None
    claim_grounding_rate: float | None = None
    n_mentions: int = 0
    no_mention_case: bool = False
    # D-01 v4 — lớp retrieval / fusion
    retrieval_entity_recall: float | None = None
    retrieval_hit: float | None = None
    fusion_off_graph_rate: float | None = None

    def as_dict(self, export_profile: D01ExportProfile = "internal") -> dict[str, float | int | None | bool]:
        if export_profile == "v4":
            from app.eval.fusion_eval_layers import _scores_v4_export

            return _scores_v4_export(self)
        if export_profile == "v3":
            return self.as_d01_v3_dict()
        out: dict[str, float | int | None | bool] = {
            "faithfulness": round(self.faithfulness, 4),
            "skill_accuracy": round(self.skill_accuracy, 4),
            "hallucination_rate": round(self.hallucination_rate, 4),
            "n_predicted": self.n_predicted,
            "n_gold": self.n_gold,
            "n_hallucinated": self.n_hallucinated,
            "n_mentions": self.n_mentions,
            "no_mention_case": self.no_mention_case,
        }
        if self.cosine_similarity is not None:
            out["cosine_similarity"] = round(self.cosine_similarity, 4)
        for key in (
            "ontology_f1",
            "answer_entity_f1",
            "full_grounding_rate",
            "graph_grounding_rate",
            "exclusive_graph_rate",
            "vector_only_mention_rate",
            "relation_code_recall",
            "claim_grounding_rate",
        ):
            val = getattr(self, key)
            if val is not None:
                out[key] = _round_or_none(val)
        if export_profile == "v2":
            return out
        if export_profile == "v1":
            for key in (
                "ontology_f1",
                "answer_entity_f1",
                "full_grounding_rate",
                "graph_grounding_rate",
                "exclusive_graph_rate",
                "vector_only_mention_rate",
                "relation_code_recall",
                "claim_grounding_rate",
            ):
                out.pop(key, None)
        return out

    def as_d01_v3_dict(self) -> dict[str, float | int | None | bool]:
        """Xuất metric D-01 v3 — tên rõ nghĩa, không trùng D-03 faithfulness/hallucination."""
        onto = self.ontology_f1 if self.ontology_f1 is not None else self.skill_accuracy
        ans = self.answer_entity_f1
        graph_gr = self.graph_grounding_rate
        full_gr = self.full_grounding_rate if self.full_grounding_rate is not None else self.faithfulness
        out: dict[str, float | int | None | bool] = {
            "answer_entity_f1": _round_or_none(ans),
            "ontology_f1": _round_or_none(onto),
            "graph_entity_grounding": _round_or_none(graph_gr),
            "off_graph_mention_rate": round(self.hallucination_rate, 4),
            "vector_only_mention_rate": _round_or_none(self.vector_only_mention_rate),
            "exclusive_graph_rate": _round_or_none(self.exclusive_graph_rate),
            "context_entity_grounding": _round_or_none(full_gr),
            "n_predicted": self.n_predicted,
            "n_gold": self.n_gold,
            "n_off_graph_mentions": self.n_hallucinated,
            "n_mentions": self.n_mentions,
            "no_mention_case": self.no_mention_case,
        }
        if self.cosine_similarity is not None:
            out["cosine_similarity"] = round(self.cosine_similarity, 4)
        if self.relation_code_recall is not None:
            out["relation_code_recall"] = _round_or_none(self.relation_code_recall)
        if self.claim_grounding_rate is not None:
            out["claim_grounding_rate"] = _round_or_none(self.claim_grounding_rate)
        return out


def _norm_set(labels: Iterable[str]) -> set[str]:
    return {normalize_skill_label(x) for x in labels if x and str(x).strip()}


def skill_recall(predicted: Iterable[str], gold: Iterable[str]) -> tuple[float, int, int]:
    """Recall = |pred ∩ gold| / |gold|."""
    pred = _norm_set(predicted)
    g = _norm_set(gold)
    if not g:
        return 1.0, len(pred), 0
    hit = len(pred & g)
    return hit / len(g), len(pred), len(g)


def skill_f1(predicted: Iterable[str], gold: Iterable[str]) -> float:
    pred = _norm_set(predicted)
    g = _norm_set(gold)
    if not g and not pred:
        return 1.0
    if not g:
        return 0.0
    if not pred:
        return 0.0
    hit = len(pred & g)
    precision = hit / len(pred)
    recall = hit / len(g)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def entities_from_graph(graph: dict[str, Any] | None) -> set[str]:
    """Thu thập entity (skill/course) được phép từ graph snapshot."""
    allowed: set[str] = set()
    if not graph:
        return allowed

    for key in ("competencies", "skills_missing", "skills_known"):
        for item in graph.get(key) or []:
            if isinstance(item, dict):
                name = item.get("name")
                code = item.get("code") or item.get("item_code")
                if name:
                    allowed.add(normalize_skill_label(str(name)))
                if code:
                    allowed.add(normalize_skill_label(str(code)))

    if graph.get("career_name"):
        allowed.add(normalize_skill_label(str(graph["career_name"])))
    if graph.get("career_code"):
        allowed.add(normalize_skill_label(str(graph["career_code"])))
    if graph.get("competency_name"):
        allowed.add(normalize_skill_label(str(graph["competency_name"])))

    for course in graph.get("courses") or []:
        if not isinstance(course, dict):
            continue
        for field in ("course_name", "course_code", "organization", "level"):
            val = course.get(field)
            if val:
                allowed.add(normalize_skill_label(str(val)))

    for code in extract_course_codes_from_snapshot(graph):
        allowed.add(normalize_skill_label(code))

    for bucket in ("outgoing", "incoming"):
        for edge in graph.get(bucket) or []:
            if not isinstance(edge, dict):
                continue
            for key in ("to_code", "from_code", "to_name", "from_name"):
                val = edge.get(key)
                if val:
                    allowed.add(normalize_skill_label(str(val)))
    if graph.get("anchor_code"):
        allowed.add(normalize_skill_label(str(graph["anchor_code"])))
    if graph.get("anchor_name"):
        allowed.add(normalize_skill_label(str(graph["anchor_name"])))

    return {x for x in allowed if x}


def entities_from_vector_docs(vector_docs: Iterable[Any]) -> set[str]:
    allowed: set[str] = set()
    for doc in vector_docs:
        payload = getattr(doc, "payload", None) or {}
        if not isinstance(payload, dict):
            continue
        for field in (
            "title",
            "canonical_id",
            "career_name",
            "career_code",
            "item_name",
            "item_code",
            "course_name",
            "course_code",
        ):
            val = payload.get(field)
            if val:
                allowed.add(normalize_skill_label(str(val)))
        for comp in payload.get("competencies") or []:
            if isinstance(comp, dict):
                for k in ("item_name", "item_code", "name", "code"):
                    if comp.get(k):
                        allowed.add(normalize_skill_label(str(comp[k])))
            elif isinstance(comp, str):
                allowed.add(normalize_skill_label(comp))
        text = getattr(doc, "text", "") or payload.get("text") or ""
        for token in _TOKEN_RE.findall(str(text)):
            if len(token) >= 3:
                allowed.add(normalize_skill_label(token))
    return {x for x in allowed if x}


def extract_mentions_from_reply(reply: str, candidate_vocab: set[str]) -> set[str]:
    """
    Tìm entity được nhắc trong reply bằng cách khớp với vocab ngữ cảnh.
    Tránh false-positive: chỉ chấp nhận mention nếu nằm trong candidate_vocab.
    """
    if not reply or not candidate_vocab:
        return set()

    reply_norm = normalize_skill_label(reply)
    mentions: set[str] = set()

    # Sắp xếp vocab dài trước để ưu tiên "React Native" hơn "React".
    for entity in sorted(candidate_vocab, key=len, reverse=True):
        if len(entity) < 2:
            continue
        if entity in reply_norm:
            mentions.add(entity)

    for code in _COURSE_CITE_RE.findall(reply):
        mentions.add(normalize_skill_label(code))

    return mentions


def compute_quality_scores(
    *,
    reply: str,
    predicted_entities: Iterable[str],
    gold_entities: Iterable[str],
    context_entities: Iterable[str],
    graph_snapshot: dict[str, Any] | None = None,
    empty_reply_penalty: bool = False,
    min_reply_chars: int = 8,
    no_mention_policy: NoMentionPolicy = "legacy_one",
) -> QualityScores:
    """
    Tính 3 chỉ số D-01:
    - faithfulness: tỷ lệ mention trong reply nằm trong context
    - skill_accuracy: F1 giữa predicted vs gold (pathfinding: skills, course_rec: courses)
    - hallucination_rate: % mention không có trong context
    """
    ctx = _norm_set(context_entities)
    ctx |= entities_from_graph(graph_snapshot)

    vocab = set(ctx)
    vocab |= _norm_set(predicted_entities)
    vocab |= _norm_set(gold_entities)

    mentions = extract_mentions_from_reply(reply, vocab)
    if not mentions:
        mentions = _norm_set(predicted_entities)

    n_mentions = len(mentions)
    no_mention_case = n_mentions == 0
    if n_mentions == 0:
        policy = no_mention_policy
        if policy == "legacy_one" and not (
            empty_reply_penalty and len(str(reply or "").strip()) < min_reply_chars
        ):
            faithfulness = 1.0
            hallucination_rate = 0.0
            n_hallucinated = 0
        elif policy == "exclude":
            faithfulness = 0.0
            hallucination_rate = 0.0
            n_hallucinated = 0
        else:
            faithfulness = 0.0
            hallucination_rate = 0.0
            n_hallucinated = 0
    else:
        grounded = {m for m in mentions if m in ctx}
        faithfulness = len(grounded) / n_mentions
        n_hallucinated = n_mentions - len(grounded)
        hallucination_rate = n_hallucinated / n_mentions

    skill_accuracy = skill_f1(predicted_entities, gold_entities)
    _, n_pred, n_gold = skill_recall(predicted_entities, gold_entities)

    return QualityScores(
        faithfulness=faithfulness,
        skill_accuracy=skill_accuracy,
        hallucination_rate=hallucination_rate,
        n_predicted=n_pred,
        n_gold=n_gold,
        n_hallucinated=n_hallucinated,
        n_mentions=n_mentions,
        no_mention_case=no_mention_case,
    )


def _mention_rate(mentions: set[str], allowed: set[str]) -> float | None:
    if not mentions:
        return None
    grounded = {m for m in mentions if m in allowed}
    return len(grounded) / len(mentions)


def relation_code_recall(predicted: Iterable[str], gold: Iterable[str]) -> float:
    """Recall trên mã competency (CT_*, FRAM_*, …) — không qua normalize_skill_label."""
    pred = {str(x).strip().upper() for x in predicted if x and str(x).strip()}
    g = {str(x).strip().upper() for x in gold if x and str(x).strip()}
    if not g:
        return 1.0
    if not pred:
        return 0.0
    return len(pred & g) / len(g)


def claim_grounding_rate(reply: str, allowed_entities: Iterable[str]) -> float | None:
    """
    D-09 — Tỉ lệ câu có >=2 entity mention mà mọi mention đều nằm trong graph context.
    """
    allowed = _norm_set(allowed_entities)
    if not allowed:
        return None
    sentences = re.split(r"[.!?\n]+", str(reply or ""))
    claims = 0
    grounded = 0
    for sent in sentences:
        if not sent.strip():
            continue
        mentions = extract_mentions_from_reply(sent, allowed)
        if len(mentions) < 2:
            continue
        claims += 1
        if mentions.issubset(allowed):
            grounded += 1
    if claims == 0:
        return None
    return grounded / claims


def compute_quality_scores_v2(
    *,
    reply: str,
    predicted_entities: Iterable[str],
    gold_entities: Iterable[str],
    graph_context: Iterable[str],
    vector_context: Iterable[str],
    graph_snapshot: dict[str, Any] | None = None,
    no_mention_policy: NoMentionPolicy = "penalize",
) -> QualityScores:
    """
    D-01 V2 metrics with separate graph/vector contexts.
    Rate metrics return None when |mentions| == 0 (excluded from aggregate mean).
    """
    graph_ctx = _norm_set(graph_context)
    graph_ctx |= entities_from_graph(graph_snapshot)
    vector_ctx = _norm_set(vector_context)

    full_ctx = graph_ctx | vector_ctx
    vocab = set(full_ctx)
    vocab |= _norm_set(predicted_entities)
    vocab |= _norm_set(gold_entities)

    mentions = extract_mentions_from_reply(reply, vocab)
    if not mentions:
        mentions = _norm_set(predicted_entities)

    n_mentions = len(mentions)
    no_mention_case = n_mentions == 0
    ontology_f1 = skill_f1(predicted_entities, gold_entities)
    answer_entity_f1 = skill_f1(mentions, gold_entities)

    if n_mentions == 0:
        if no_mention_policy == "legacy_one":
            full_grounding_rate = 1.0
            graph_grounding_rate = 1.0
            exclusive_graph_rate = 0.0
            vector_only_mention_rate = 0.0
            hallucination_rate = 0.0
            n_hallucinated = 0
        else:
            full_grounding_rate = None
            graph_grounding_rate = None
            exclusive_graph_rate = None
            vector_only_mention_rate = None
            hallucination_rate = 0.0
            n_hallucinated = 0
    else:
        full_grounding_rate = _mention_rate(mentions, full_ctx)
        graph_grounding_rate = _mention_rate(mentions, graph_ctx)
        exclusive = {m for m in mentions if m in graph_ctx and m not in vector_ctx}
        exclusive_graph_rate = len(exclusive) / n_mentions
        vector_only = {m for m in mentions if m in vector_ctx and m not in graph_ctx}
        vector_only_mention_rate = len(vector_only) / n_mentions
        graph_hallucinated = {m for m in mentions if m not in graph_ctx}
        n_hallucinated = len(graph_hallucinated)
        hallucination_rate = n_hallucinated / n_mentions

    _, n_pred, n_gold = skill_recall(predicted_entities, gold_entities)
    rel_recall = relation_code_recall(predicted_entities, gold_entities)
    claim_gr = claim_grounding_rate(reply, graph_ctx)

    return QualityScores(
        faithfulness=full_grounding_rate if full_grounding_rate is not None else 0.0,
        skill_accuracy=ontology_f1,
        hallucination_rate=hallucination_rate,
        n_predicted=n_pred,
        n_gold=n_gold,
        n_hallucinated=n_hallucinated,
        n_mentions=n_mentions,
        ontology_f1=ontology_f1,
        answer_entity_f1=answer_entity_f1,
        full_grounding_rate=full_grounding_rate,
        graph_grounding_rate=graph_grounding_rate,
        exclusive_graph_rate=exclusive_graph_rate,
        vector_only_mention_rate=vector_only_mention_rate,
        relation_code_recall=rel_recall if n_gold else None,
        claim_grounding_rate=claim_gr,
        no_mention_case=no_mention_case,
    )


def _mean_optional(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def average_scores(rows: list[QualityScores]) -> QualityScores:
    if not rows:
        return QualityScores(faithfulness=0.0, skill_accuracy=0.0, hallucination_rate=0.0)
    n = len(rows)
    cos_rows = [r.cosine_similarity for r in rows if r.cosine_similarity is not None]
    mean_cos = sum(cos_rows) / len(cos_rows) if cos_rows else None

    has_v2 = any(r.ontology_f1 is not None for r in rows)
    full_gr = _mean_optional([r.full_grounding_rate for r in rows])
    scored = [r for r in rows if not r.no_mention_case or r.full_grounding_rate is not None]
    faithfulness_pool = scored if scored else rows
    faithfulness = full_gr if full_gr is not None else sum(r.faithfulness for r in faithfulness_pool) / len(
        faithfulness_pool
    )

    return QualityScores(
        faithfulness=faithfulness,
        skill_accuracy=sum(r.skill_accuracy for r in rows) / n,
        hallucination_rate=sum(r.hallucination_rate for r in rows) / n,
        n_predicted=sum(r.n_predicted for r in rows),
        n_gold=sum(r.n_gold for r in rows),
        n_hallucinated=sum(r.n_hallucinated for r in rows),
        n_mentions=sum(r.n_mentions for r in rows),
        cosine_similarity=mean_cos,
        ontology_f1=_mean_optional([r.ontology_f1 for r in rows]) if has_v2 else None,
        answer_entity_f1=_mean_optional([r.answer_entity_f1 for r in rows]) if has_v2 else None,
        full_grounding_rate=full_gr,
        graph_grounding_rate=_mean_optional([r.graph_grounding_rate for r in rows])
        if has_v2
        else None,
        exclusive_graph_rate=_mean_optional([r.exclusive_graph_rate for r in rows])
        if has_v2
        else None,
        vector_only_mention_rate=_mean_optional([r.vector_only_mention_rate for r in rows])
        if has_v2
        else None,
        relation_code_recall=_mean_optional([r.relation_code_recall for r in rows])
        if has_v2
        else None,
        claim_grounding_rate=_mean_optional([r.claim_grounding_rate for r in rows])
        if has_v2
        else None,
        retrieval_entity_recall=_mean_optional([r.retrieval_entity_recall for r in rows]),
        retrieval_hit=_mean_optional([r.retrieval_hit for r in rows]),
        fusion_off_graph_rate=_mean_optional([r.fusion_off_graph_rate for r in rows]),
    )


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Cosine similarity giữa hai vector embedding (0..1 khi cùng chiều)."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def embedding_text_similarity(
    embedder: EmbeddingClient,
    text_a: str,
    text_b: str,
) -> float | None:
    """Cosine similarity embedding giữa hai đoạn văn bản."""
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if not a or not b or not embedder.available:
        return None
    try:
        vecs = embedder.embed([a, b])
        if len(vecs) != 2:
            return None
        return cosine_similarity(vecs[0], vecs[1])
    except Exception:
        return None


def build_gold_reference_text(item: dict[str, Any]) -> str:
    """Văn bản mẫu từ gold set — dùng cho cosine similarity (generative mode)."""
    if item.get("gold_reply"):
        return str(item["gold_reply"]).strip()
    intent = str(item.get("intent") or "")
    if intent == "pathfinding":
        skills = item.get("gold_skills") or []
        career = item.get("career") or item.get("target_career") or "nghề mục tiêu"
        if skills:
            return (
                f"Lộ trình {career} cần các kỹ năng và công cụ: "
                + ", ".join(str(s) for s in skills[:20])
                + "."
            )
        return f"Tư vấn lộ trình cho {career}."
    if intent == "course_rec":
        codes = item.get("gold_course_codes") or []
        comp = item.get("competency") or item.get("gold_competency") or "kỹ năng"
        if codes:
            return (
                f"Khóa học gợi ý cho {comp} (mã): "
                + ", ".join(str(c) for c in codes[:15])
                + "."
            )
        return f"Gợi ý khóa học cho {comp}."
    if intent == "competency_relation":
        codes = item.get("gold_related_codes") or []
        comp = item.get("competency") or item.get("anchor") or "competency"
        if codes:
            return (
                f"Quan hệ của {comp} với: "
                + ", ".join(str(c) for c in codes[:15])
                + "."
            )
        return f"Giải thích quan hệ competency cho {comp}."
    return str(item.get("query") or "")


def score_dict_get(scores: dict[str, Any], canonical: str, default: float = 0.0) -> float:
    """Đọc metric từ dict export v3 hoặc legacy v1/v2."""
    aliases: dict[str, tuple[str, ...]] = {
        "answer_entity_f1": ("answer_entity_f1",),
        "ontology_f1": ("ontology_f1", "skill_accuracy"),
        "graph_entity_grounding": ("graph_entity_grounding", "graph_grounding_rate", "faithfulness"),
        "off_graph_mention_rate": ("off_graph_mention_rate", "hallucination_rate"),
        "context_entity_grounding": ("context_entity_grounding", "full_grounding_rate", "faithfulness"),
    }
    for key in aliases.get(canonical, (canonical,)):
        val = scores.get(key)
        if val is not None:
            return float(val)
    return default


def classify_error_tags(
    *,
    faithfulness: float | None = None,
    skill_accuracy: float | None = None,
    hallucination_rate: float | None = None,
    ontology_f1: float | None = None,
    off_graph_mention_rate: float | None = None,
    graph_entity_grounding: float | None = None,
    reply: str,
) -> list[str]:
    """
    Phân loại lỗi tự động D-01: omission | off_graph_noise | format.
  off_graph_noise = mention lệch graph (không phải ảo giác LLM).
    """
    skill = ontology_f1 if ontology_f1 is not None else (skill_accuracy if skill_accuracy is not None else 0.0)
    off_graph = (
        off_graph_mention_rate
        if off_graph_mention_rate is not None
        else (hallucination_rate if hallucination_rate is not None else 0.0)
    )
    graph_gr = (
        graph_entity_grounding
        if graph_entity_grounding is not None
        else (faithfulness if faithfulness is not None else 1.0)
    )
    tags: list[str] = []
    if skill < 0.35:
        tags.append("omission")
    if off_graph > 0.15 or graph_gr < 0.6:
        tags.append("off_graph_noise")
    text = (reply or "").strip()
    if len(text) < 20:
        tags.append("format")
    elif text.count("```") >= 2 or text.count("##") > 8:
        tags.append("format")
    return tags
