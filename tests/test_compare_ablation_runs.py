from scripts.compare_ablation_runs import compare_reports


def _mini_report(case_id: str, mode: str, f1: float) -> dict:
    return {
        "details": [
            {
                "case_id": case_id,
                "mode": mode,
                "scores": {"answer_entity_f1": f1},
            }
        ]
    }


def test_compare_filters_baseline_to_candidate_case_ids():
    baseline = {
        "details": [
            {"case_id": "a", "mode": "graph_only", "scores": {"answer_entity_f1": 0.8}},
            {"case_id": "b", "mode": "graph_only", "scores": {"answer_entity_f1": 0.9}},
        ]
    }
    candidate = _mini_report("a", "graph_only", 0.75)
    result = compare_reports(
        baseline,
        candidate,
        metrics=["answer_entity_f1"],
        filter_baseline_to_candidate=True,
    )
    assert result["n_paired"] == 1
    assert result["summary_delta_by_mode"]["graph_only"]["answer_entity_f1"] == -0.05


def test_compare_detects_regression_drop():
    baseline = _mini_report("x", "tight_fusion", 0.9)
    candidate = _mini_report("x", "tight_fusion", 0.5)
    result = compare_reports(
        baseline,
        candidate,
        metrics=["answer_entity_f1"],
        filter_baseline_to_candidate=False,
        regression_f1_drop=0.15,
    )
    assert result["n_regressions_f1_drop"] == 1
