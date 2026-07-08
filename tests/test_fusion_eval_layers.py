"""D-01 v4 — layered fusion evaluation metrics."""

from app.eval.ablation_pipeline import FusionMode
from app.eval.fusion_eval_layers import (
    compute_fusion_layer_scores,
    gold_answer_entities,
    gold_retrieval_entities,
    summarize_v4_layers,
)
from app.eval.quality_metrics import entities_from_graph


def test_gold_retrieval_course_rec_uses_codes():
    item = {
        "intent": "course_rec",
        "gold_course_codes": ["CRS_PY_01"],
    }
    assert gold_retrieval_entities(item) == ["CRS_PY_01"]


def test_gold_answer_course_rec_includes_name_from_graph():
    item = {"intent": "course_rec", "gold_course_codes": ["CRS_PY_01"]}
    graph = {
        "courses": [
            {"course_code": "CRS_PY_01", "course_name": "Python Fundamentals"},
        ]
    }
    gold_a = gold_answer_entities(item, graph)
    assert "CRS_PY_01" in gold_a
    assert "Python Fundamentals" in gold_a


def test_vector_only_no_graph_grounding_not_zero_sentinel():
    graph = {
        "competencies": [{"name": "Python"}, {"name": "SQL"}],
    }
    ctx = entities_from_graph(graph)
    scores = compute_fusion_layer_scores(
        reply="Cần Python và SQL.",
        predicted_entities=["Python", "SQL"],
        item={"intent": "pathfinding", "gold_skills": ["Python", "SQL", "Docker"]},
        graph_context=set(),
        vector_context=ctx,
        graph_snapshot=None,
        fusion_mode=FusionMode.VECTOR_ONLY,
    )
    assert scores.graph_grounding_rate is None
    assert scores.fusion_off_graph_rate is None
    assert scores.retrieval_entity_recall is not None
    assert scores.retrieval_hit == 1.0


def test_graph_only_has_zero_off_graph_not_na():
    graph = {
        "competencies": [{"name": "Python"}, {"name": "SQL"}],
    }
    ctx = entities_from_graph(graph)
    scores = compute_fusion_layer_scores(
        reply="Cần Python và SQL.",
        predicted_entities=["Python", "SQL"],
        item={"intent": "pathfinding", "gold_skills": ["Python", "SQL"]},
        graph_context=ctx,
        vector_context=set(),
        graph_snapshot=graph,
        fusion_mode=FusionMode.GRAPH_ONLY,
    )
    assert scores.fusion_off_graph_rate == 0.0
    assert scores.graph_grounding_rate == 1.0


def test_summarize_v4_layers_structure():
    details = [
        {
            "case_id": "pf1",
            "mode": "vector_only",
            "intent": "pathfinding",
            "scores": {
                "retrieval_entity_f1": 0.1,
                "retrieval_hit": 1.0,
                "answer_entity_f1": 0.05,
                "fusion_off_graph_rate": None,
                "graph_entity_grounding": None,
            },
        },
        {
            "case_id": "pf1",
            "mode": "tight_fusion",
            "intent": "pathfinding",
            "scores": {
                "retrieval_entity_f1": 0.8,
                "retrieval_hit": 1.0,
                "answer_entity_f1": 0.6,
                "fusion_off_graph_rate": 0.3,
                "graph_entity_grounding": 0.7,
            },
        },
    ]
    out = summarize_v4_layers(details, modes=list(FusionMode))
    assert "layer1_retrieval_all_intents" in out
    assert "vector_only" in out["layer1_retrieval_all_intents"]
    assert "tight_fusion" in out["layer3_fusion_reply_pathfinding"]
