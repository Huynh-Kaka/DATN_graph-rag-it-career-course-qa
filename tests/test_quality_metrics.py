from app.eval.quality_metrics import (
    average_scores,
    build_gold_reference_text,
    classify_error_tags,
    compute_quality_scores,
    compute_quality_scores_v2,
    cosine_similarity,
    entities_from_graph,
    skill_f1,
    skill_recall,
)


def test_skill_recall_partial():
    recall, n_pred, n_gold = skill_recall(["Python", "SQL"], ["Python", "Java", "Git"])
    assert recall == 1 / 3
    assert n_pred == 2
    assert n_gold == 3


def test_skill_f1_perfect():
    assert skill_f1(["Python", "SQL"], ["python", "sql"]) == 1.0


def test_faithfulness_grounded_reply():
    graph = {
        "found": True,
        "competencies": [{"name": "Python"}, {"name": "SQL"}],
        "courses": [{"course_code": "PY101", "course_name": "Python 101"}],
    }
    context = entities_from_graph(graph)
    scores = compute_quality_scores(
        reply="Cần học Python và SQL. Khóa [Course: PY101].",
        predicted_entities=["Python", "SQL"],
        gold_entities=["Python", "SQL", "Docker"],
        context_entities=context,
        graph_snapshot=graph,
    )
    assert scores.faithfulness == 1.0
    assert scores.hallucination_rate == 0.0
    assert scores.skill_accuracy > 0.5


def test_gold_reference_course_rec():
    ref = build_gold_reference_text(
        {
            "intent": "course_rec",
            "competency": "Python",
            "gold_course_codes": ["PY101", "PY102"],
        }
    )
    assert "PY101" in ref
    assert "Python" in ref


def test_classify_error_tags_clean_reply():
    tags = classify_error_tags(
        faithfulness=1.0,
        skill_accuracy=0.9,
        hallucination_rate=0.0,
        reply="Đủ dài để không bị gắn nhãn format lỗi cho câu trả lời hợp lệ.",
    )
    assert tags == []


def test_cosine_same_direction():
    assert cosine_similarity([1, 2, 3], [2, 4, 6]) == 1.0


def test_hallucination_detected():
    graph = {"competencies": [{"name": "Python"}]}
    context = entities_from_graph(graph)
    scores = compute_quality_scores(
        reply="Học Rust và Go ngay.",
        predicted_entities=["Rust", "Go"],
        gold_entities=["Python"],
        context_entities=context,
        graph_snapshot=graph,
    )
    assert scores.hallucination_rate == 1.0
    assert scores.faithfulness == 0.0


def test_course_rec_answer_entity_f1_with_course_citations():
    """D-01 v3.1: [Course: CODE] trong reply ablation khớp gold_course_codes."""
    graph = {
        "courses": [
            {"course_code": "CRS_FRAM_F_FLUTTER_01", "course_name": "Flutter cơ bản"},
        ]
    }
    graph_ctx = entities_from_graph(graph)
    reply_with_cite = "[Course: CRS_FRAM_F_FLUTTER_01]"
    reply_name_only = "Khóa Flutter cơ bản trên Udemy"
    gold = ["CRS_FRAM_F_FLUTTER_01"]

    with_cite = compute_quality_scores_v2(
        reply=reply_with_cite,
        predicted_entities=gold,
        gold_entities=gold,
        graph_context=graph_ctx,
        vector_context=set(),
        graph_snapshot=graph,
    )
    name_only = compute_quality_scores_v2(
        reply=reply_name_only,
        predicted_entities=gold,
        gold_entities=gold,
        graph_context=graph_ctx,
        vector_context=set(),
        graph_snapshot=graph,
    )
    assert with_cite.answer_entity_f1 == 1.0
    assert name_only.answer_entity_f1 == 0.0


def test_v2_ontology_high_answer_entity_low():
    graph = {
        "competencies": [{"name": "Python"}, {"name": "SQL"}, {"name": "Docker"}],
    }
    graph_ctx = entities_from_graph(graph)
    scores = compute_quality_scores_v2(
        reply="Cần học Python.",
        predicted_entities=["Python", "SQL", "Docker"],
        gold_entities=["Python", "SQL", "Docker"],
        graph_context=graph_ctx,
        vector_context=set(),
        graph_snapshot=graph,
    )
    assert scores.ontology_f1 == 1.0
    assert scores.answer_entity_f1 is not None
    assert scores.answer_entity_f1 < 1.0


def test_v2_exclusive_graph_rate_zero_mentions_is_none():
    scores = compute_quality_scores_v2(
        reply="",
        predicted_entities=[],
        gold_entities=["Python"],
        graph_context={"python"},
        vector_context=set(),
        graph_snapshot=None,
        no_mention_policy="penalize",
    )
    assert scores.exclusive_graph_rate is None
    assert scores.n_mentions == 0
    assert scores.no_mention_case is True
    assert scores.faithfulness == 0.0


def test_no_mention_penalize_v1():
    scores = compute_quality_scores(
        reply="",
        predicted_entities=[],
        gold_entities=["Python", "SQL"],
        context_entities={"python"},
        graph_snapshot=None,
        no_mention_policy="penalize",
    )
    assert scores.no_mention_case is True
    assert scores.faithfulness == 0.0


def test_v3_export_dict_renames_legacy_metrics():
    from app.eval.quality_metrics import QualityScores

    scores = QualityScores(
        faithfulness=1.0,
        skill_accuracy=0.8674,
        hallucination_rate=0.45,
        ontology_f1=0.8674,
        answer_entity_f1=0.3958,
        graph_grounding_rate=0.5482,
        full_grounding_rate=1.0,
        vector_only_mention_rate=0.4518,
        exclusive_graph_rate=0.4983,
    )
    exported = scores.as_d01_v3_dict()
    assert "faithfulness" not in exported
    assert "hallucination_rate" not in exported
    assert exported["answer_entity_f1"] == 0.3958
    assert exported["ontology_f1"] == 0.8674
    assert exported["off_graph_mention_rate"] == 0.45
    assert exported["graph_entity_grounding"] == 0.5482
    assert exported["context_entity_grounding"] == 1.0


def test_v2_average_skips_none_rates():
    from app.eval.quality_metrics import QualityScores

    rows = [
        QualityScores(
            faithfulness=1.0,
            skill_accuracy=1.0,
            hallucination_rate=0.0,
            exclusive_graph_rate=0.5,
            ontology_f1=1.0,
        ),
        QualityScores(
            faithfulness=0.0,
            skill_accuracy=0.0,
            hallucination_rate=1.0,
            exclusive_graph_rate=None,
            ontology_f1=0.0,
        ),
    ]
    avg = average_scores(rows)
    assert avg.exclusive_graph_rate == 0.5
