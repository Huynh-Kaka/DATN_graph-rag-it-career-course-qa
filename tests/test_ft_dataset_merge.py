import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ft_dataset_utils import (
    dedup_rows,
    infer_entity_key,
    load_ft_rows,
    merge_sources,
    split_by_entity,
    write_ft_jsonl,
)


def _row(question: str, entity: str, *, message_id: int | None = None, source: str = "synthetic"):
    snap = json.dumps({"found": True, "career_name": entity}, ensure_ascii=False)
    meta = {"source": source, "intent": "pathfinding", "entity_key": entity.lower()}
    if message_id is not None:
        meta["message_id"] = message_id
    return {
        "intent": "pathfinding",
        "entity_key": entity.lower(),
        "messages": [
            {"role": "system", "content": "pathfinding system"},
            {
                "role": "user",
                "content": f"## Câu hỏi\n{question}\n\n## Dữ liệu Neo4j\n{snap}",
            },
            {"role": "assistant", "content": "reply"},
        ],
        "meta": meta,
    }


def test_dedup_prefers_chat_over_synthetic():
    synth = _row("Lộ trình Backend?", "Backend Developer", source="synthetic")
    chat = _row("Lộ trình Backend?", "Backend Developer", message_id=99, source="chat")
    out = dedup_rows([synth, chat])
    assert len(out) == 1
    assert out[0]["meta"]["message_id"] == 99


def test_split_by_entity_keeps_entity_in_one_split():
    rows = [_row(f"Q{i}?", "Career A") for i in range(5)]
    train, val = split_by_entity(rows)
    assert len(train) + len(val) == 5
    assert len(val) >= 1


def test_merge_sources_from_dirs(tmp_path: Path):
    chat_dir = tmp_path / "chat"
    syn_dir = tmp_path / "syn"
    chat_dir.mkdir()
    syn_dir.mkdir()
    write_ft_jsonl(
        chat_dir / "ft_generator_pathfinding_train.jsonl",
        [_row("Chat Q?", "Backend Developer", message_id=1, source="chat")],
    )
    write_ft_jsonl(
        syn_dir / "ft_generator_pathfinding_train.jsonl",
        [_row("Synth Q?", "Software Engineer", source="synthetic")],
    )
    merged = merge_sources([chat_dir, syn_dir])
    train, val = merged["pathfinding"]
    assert len(train) + len(val) == 2


def test_load_ft_rows_roundtrip(tmp_path: Path):
    path = tmp_path / "ft_generator_pathfinding_train.jsonl"
    row = _row("Roundtrip?", "DevOps Engineer", source="synthetic")
    write_ft_jsonl(path, [row])
    loaded = load_ft_rows(path)
    assert len(loaded) == 1
    assert infer_entity_key(loaded[0]["messages"], loaded[0]["meta"]) == "devops engineer"
