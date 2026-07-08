"""Tests for competency_relation registry, topo-sort, and eval metrics."""

from __future__ import annotations

from app.eval.quality_metrics import relation_code_recall
from app.graph.models import CompetencyItem
from app.graph.relation_registry import get_relation_registry
from app.graph.skills_gap import safe_topo_sort


def test_relation_registry_known_types():
    reg = get_relation_registry()
    types = reg.known_relation_types()
    assert "BUILT_ON" in types
    assert "REQUIRES_KNOWLEDGE" in types
    assert reg.get_direction("CT_FRAM", "BUILT_ON") == "outgoing"
    assert reg.get_direction("CT_PLAT", "VALIDATES") == "incoming"
    assert "BUILT_ON" in reg.ordering_rel_types()


def test_registry_validate_excel_row_ok():
    reg = get_relation_registry()
    errors = reg.validate_excel_row(
        {
            "relation_type": "BUILT_ON",
            "from_type_code": "CT_FRAM",
            "to_type_code": "CT_LANG",
            "from_item_code": "F_REACT",
            "to_item_code": "L_JS",
        }
    )
    assert errors == []


def test_registry_validate_unknown_type():
    reg = get_relation_registry()
    errors = reg.validate_excel_row(
        {
            "relation_type": "UNKNOWN",
            "from_item_code": "A",
            "to_item_code": "B",
        }
    )
    assert any("unknown" in e for e in errors)


def test_safe_topo_sort_cycle_degrades():
    nodes = [
        CompetencyItem(name="A", code="S_A", kind="Softskill", priority=1),
        CompetencyItem(name="B", code="S_B", kind="Softskill", priority=2),
    ]
    edges = [("S_A", "S_B"), ("S_B", "S_A")]
    ordered, had_cycle = safe_topo_sort(nodes, edges)
    assert had_cycle is True
    assert len(ordered) == 2


def test_safe_topo_sort_orders_prerequisites():
    nodes = [
        CompetencyItem(name="React", code="F_REACT", kind="Framework", priority=2),
        CompetencyItem(name="JavaScript", code="L_JS", kind="ProgrammingLanguage", priority=1),
    ]
    edges = [("F_REACT", "L_JS")]
    ordered, had_cycle = safe_topo_sort(nodes, edges)
    assert had_cycle is False
    assert [c.code for c in ordered] == ["L_JS", "F_REACT"]


def test_relation_code_recall_exact_codes():
    assert relation_code_recall(["L_JS", "F_REACT"], ["L_JS"]) == 1.0
    assert relation_code_recall(["L_PY"], ["L_JS"]) == 0.0
    assert relation_code_recall([], ["L_JS"]) == 0.0
