"""D-01 nâng cấp: rerank A-03, course citation eval, significance, error analysis."""

from unittest.mock import MagicMock

from app.eval.ablation_pipeline import (
    FusionMode,
    _append_course_citations_for_eval,
    _post_graph_rerank_vector_docs,
)
from app.eval.error_analysis import build_error_analysis_report
from app.eval.quality_metrics import (
    build_gold_reference_text,
    classify_error_tags,
    cosine_similarity,
)
from app.rag.retriever import RetrievedDoc
from scripts.run_quality_ablation import run_significance_tests


def test_append_course_citations_adds_codes():
    graph = {"courses": [{"course_code": "CRS_LANG_L_PYTHON_01"}]}
    reply = "## Khóa Python"
    out = _append_course_citations_for_eval(reply, graph)
    assert "[Course: CRS_LANG_L_PYTHON_01]" in out


def test_post_graph_rerank_calls_retriever_with_relevant_ids():
    retriever = MagicMock()
    retriever.retrieve_docs.return_value = [
        RetrievedDoc(score=0.9, text="t", payload={"career_code": "BE"})
    ]
    graph_dump = {
        "career_code": "BE_DEV",
        "competencies": [{"code": "CT_PYTHON", "name": "Python"}],
    }
    docs = [RetrievedDoc(score=0.5, text="old", payload={})]
    out = _post_graph_rerank_vector_docs(
        retriever,
        "backend skills",
        docs,
        graph_dump,
        doc_type="career",
    )
    assert out[0].text == "t"
    kwargs = retriever.retrieve_docs.call_args.kwargs
    assert kwargs.get("relevant_ids")
    assert "CT_PYTHON" in kwargs["relevant_ids"] or "BE_DEV" in kwargs["relevant_ids"]


def test_post_graph_rerank_noop_without_graph():
    retriever = MagicMock()
    docs = [RetrievedDoc(score=0.5, text="x", payload={})]
    out = _post_graph_rerank_vector_docs(
        retriever, "q", docs, None, doc_type="career"
    )
    assert out is docs
    retriever.retrieve_docs.assert_not_called()


def test_cosine_similarity_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_build_gold_reference_from_skills():
    text = build_gold_reference_text(
        {
            "intent": "pathfinding",
            "career": "Backend Developer",
            "gold_skills": ["Python", "SQL"],
        }
    )
    assert "Python" in text
    assert "Backend Developer" in text


def test_classify_error_tags_omission_and_hallucination():
    tags = classify_error_tags(
        faithfulness=0.4,
        skill_accuracy=0.1,
        hallucination_rate=0.5,
        reply="short",
    )
    assert "omission" in tags
    assert "off_graph_noise" in tags
    assert "format" in tags


def test_significance_tests_paired_tight_vs_vector():
    details = []
    for i in range(5):
        cid = f"case_{i}"
        details.append(
            {
                "case_id": cid,
                "mode": FusionMode.TIGHT_FUSION.value,
                "scores": {"faithfulness": 0.8, "skill_accuracy": 0.7},
            }
        )
        details.append(
            {
                "case_id": cid,
                "mode": FusionMode.VECTOR_ONLY.value,
                "scores": {"faithfulness": 0.5, "skill_accuracy": 0.2},
            }
        )

    result = run_significance_tests(
        details,
        baseline_modes=[FusionMode.VECTOR_ONLY],
        metrics=["skill_accuracy"],
    )
    if result.get("available"):
        comps = result["comparisons"]
        assert comps
        assert comps[0]["paired_ttest"]["p_value"] < 0.05


def test_error_analysis_tight_beats_vector():
    details = [
        {
            "case_id": "c1",
            "mode": FusionMode.TIGHT_FUSION.value,
            "query": "Backend skills?",
            "intent": "pathfinding",
            "scores": {
                "skill_accuracy": 0.9,
                "answer_entity_f1": 0.9,
                "faithfulness": 1.0,
                "hallucination_rate": 0.0,
            },
            "error_tags": [],
            "reply_preview": "Python SQL Docker",
        },
        {
            "case_id": "c1",
            "mode": FusionMode.VECTOR_ONLY.value,
            "query": "Backend skills?",
            "intent": "pathfinding",
            "scores": {
                "skill_accuracy": 0.0,
                "answer_entity_f1": 0.0,
                "faithfulness": 0.5,
                "hallucination_rate": 0.2,
            },
            "error_tags": ["omission"],
            "reply_preview": "no match",
        },
    ]
    report = build_error_analysis_report(details)
    assert len(report["tight_fusion_beats_vector_only"]) == 1
    assert report["tight_fusion_beats_vector_only"][0]["case_id"] == "c1"
