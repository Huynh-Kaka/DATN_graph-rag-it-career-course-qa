"""Tag gold_source metadata script."""

import json
from pathlib import Path

from scripts.tag_gold_source import tag_file


def test_tag_file_adds_gold_source(tmp_path: Path):
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        json.dumps({"id": "a", "intent": "pathfinding", "query": "q"}) + "\n",
        encoding="utf-8",
    )
    tag_file(gold, "derived_from_graph_repository")
    row = json.loads(gold.read_text(encoding="utf-8").strip())
    assert row["gold_source"] == "derived_from_graph_repository"


def test_tag_file_preserves_existing_source(tmp_path: Path):
    gold = tmp_path / "gold.jsonl"
    gold.write_text(
        json.dumps({"id": "a", "gold_source": "excel_derived"}) + "\n",
        encoding="utf-8",
    )
    tag_file(gold, "derived_from_graph_repository")
    row = json.loads(gold.read_text(encoding="utf-8").strip())
    assert row["gold_source"] == "excel_derived"
