"""Shared helpers for fine-tune JSONL export, synthetic build, and merge."""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

INTENTS = ("pathfinding", "course_rec")

_FT_NAME_RE = re.compile(
    r"ft_generator_(?P<intent>pathfinding|course_rec)_(?P<split>train|val)\.jsonl$"
)
_NEO4J_BLOCK_RE = re.compile(r"## Dữ liệu Neo4j\s*\n(?P<json>\{.*\})\s*\Z", re.DOTALL)
_QUESTION_RE = re.compile(r"## Câu hỏi\s*\n(?P<q>.+?)(?:\n\n|\Z)", re.DOTALL)


def ft_paths(out_dir: Path, intent: str) -> tuple[Path, Path]:
    return (
        out_dir / f"ft_generator_{intent}_train.jsonl",
        out_dir / f"ft_generator_{intent}_val.jsonl",
    )


def _parse_neo4j_snapshot(user_content: str) -> dict[str, Any]:
    match = _NEO4J_BLOCK_RE.search(user_content or "")
    if not match:
        return {}
    try:
        data = json.loads(match.group("json"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def infer_entity_key(messages: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> str:
    meta = meta or {}
    for key in ("entity_key", "career", "competency"):
        val = meta.get(key)
        if val:
            return str(val).lower()
    user_content = messages[1].get("content", "") if len(messages) > 1 else ""
    snap = _parse_neo4j_snapshot(user_content)
    entity = snap.get("career_name") or snap.get("competency_name") or "unknown"
    return str(entity).lower()


def infer_intent(
    messages: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
    *,
    filename: str | None = None,
) -> str | None:
    meta = meta or {}
    intent = meta.get("intent")
    if intent in INTENTS:
        return str(intent)
    if filename:
        m = _FT_NAME_RE.search(filename)
        if m:
            return m.group("intent")
    system = messages[0].get("content", "") if messages else ""
    if "khóa học" in system.lower() or "course" in system.lower():
        return "course_rec"
    return "pathfinding"


def dedup_key(row: dict[str, Any]) -> str:
    """Khóa gộp theo entity + câu hỏi — chat và synthetic trùng nội dung chỉ giữ một."""
    messages = row.get("messages") or []
    meta = row.get("meta") or {}
    user_content = messages[1].get("content", "") if len(messages) > 1 else ""
    q_match = _QUESTION_RE.search(user_content)
    question = (q_match.group("q") if q_match else user_content).strip()
    entity = row.get("entity_key") or infer_entity_key(messages, meta)
    payload = f"{entity}\n{question}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"hash:{digest}"


def _source_priority(row: dict[str, Any]) -> int:
    source = (row.get("meta") or {}).get("source", "")
    if source == "chat":
        return 2
    if source == "synthetic":
        return 1
    if (row.get("meta") or {}).get("message_id") is not None:
        return 2
    return 0


def dedup_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = dedup_key(row)
        existing = best.get(key)
        if existing is None or _source_priority(row) > _source_priority(existing):
            best[key] = row
    return list(best.values())


def split_by_entity(
    rows: list[dict[str, Any]], *, val_ratio: float = 0.15, seed: int = 42
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        entity = row.get("entity_key") or infer_entity_key(
            row.get("messages") or [], row.get("meta")
        )
        row["entity_key"] = entity
        by_entity.setdefault(entity, []).append(row)

    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    rng = random.Random(seed)
    for items in by_entity.values():
        rng.shuffle(items)
        n_val = max(1, int(len(items) * val_ratio)) if len(items) >= 4 else 0
        val.extend(items[:n_val])
        train.extend(items[n_val:])
    return train, val


def load_ft_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            messages = obj.get("messages")
            if not isinstance(messages, list):
                continue
            meta = dict(obj.get("meta") or {})
            intent = infer_intent(messages, meta, filename=path.name)
            if intent not in INTENTS:
                continue
            row: dict[str, Any] = {
                "messages": messages,
                "meta": meta,
                "intent": intent,
                "entity_key": infer_entity_key(messages, meta),
            }
            rows.append(row)
    return rows


def load_ft_dir(source_dir: Path) -> dict[str, list[dict[str, Any]]]:
    by_intent: dict[str, list[dict[str, Any]]] = {i: [] for i in INTENTS}
    if not source_dir.is_dir():
        return by_intent
    for path in sorted(source_dir.glob("ft_generator_*.jsonl")):
        for row in load_ft_rows(path):
            by_intent[row["intent"]].append(row)
    return by_intent


def write_ft_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            out: dict[str, Any] = {"messages": row["messages"]}
            meta = row.get("meta")
            if meta:
                out["meta"] = meta
            f.write(json.dumps(out, ensure_ascii=False) + "\n")


def merge_sources(
    source_dirs: list[Path],
    *,
    val_ratio: float = 0.15,
) -> dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    combined: dict[str, list[dict[str, Any]]] = {i: [] for i in INTENTS}
    for source_dir in source_dirs:
        loaded = load_ft_dir(source_dir)
        for intent in INTENTS:
            combined[intent].extend(loaded[intent])

    result: dict[str, tuple[list, list]] = {}
    for intent in INTENTS:
        unique = dedup_rows(combined[intent])
        train, val = split_by_entity(unique, val_ratio=val_ratio)
        result[intent] = (train, val)
    return result
