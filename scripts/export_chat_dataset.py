"""
Export approved / high-quality chat turns to fine-tune JSONL.

Ghi vào thư mục riêng (mặc định data/ft_from_chat); dùng merge_ft_datasets.py để gộp.

Chạy: python scripts/export_chat_dataset.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from sqlalchemy import select

from app.db.engine import database_enabled, session_scope
from app.db.enums import ReviewStatus
from app.db.models import ChatMessageModel, MessageFeedbackModel
from app.generator.prompts import COURSE_REC_SYSTEM, PATHFINDING_SYSTEM
from app.rag.paraphrase import user_prompt_keywords_block
from ft_dataset_utils import INTENTS, ft_paths, split_by_entity, write_ft_jsonl


async def _load_pairs(*, approved_only: bool) -> list[dict]:
    pairs: list[dict] = []
    async with session_scope() as db:
        stmt = (
            select(ChatMessageModel)
            .where(ChatMessageModel.role == "assistant")
            .where(ChatMessageModel.intent.in_(list(INTENTS)))
            .order_by(ChatMessageModel.id.asc())
        )
        rows = (await db.execute(stmt)).scalars().all()
        for assistant in rows:
            if assistant.intent == "_system_error":
                continue
            route = assistant.route or {}
            snap = route.get("graph_snapshot") if isinstance(route, dict) else None
            if not isinstance(snap, dict) or not snap.get("found"):
                continue
            conf = route.get("confidence") if isinstance(route, dict) else None
            if conf == "low":
                continue

            fb_stmt = select(MessageFeedbackModel).where(
                MessageFeedbackModel.message_id == assistant.id
            )
            fb = (await db.execute(fb_stmt)).scalar_one_or_none()
            if approved_only:
                if fb is None or fb.review_status != ReviewStatus.approved:
                    continue
            elif fb is not None and fb.review_status == ReviewStatus.rejected:
                continue

            user_stmt = (
                select(ChatMessageModel)
                .where(
                    ChatMessageModel.session_id == assistant.session_id,
                    ChatMessageModel.role == "user",
                    ChatMessageModel.id < assistant.id,
                )
                .order_by(ChatMessageModel.id.desc())
                .limit(1)
            )
            user_msg = (await db.execute(user_stmt)).scalar_one_or_none()
            if user_msg is None:
                continue

            intent = assistant.intent or "pathfinding"
            system = (
                PATHFINDING_SYSTEM if intent == "pathfinding" else COURSE_REC_SYSTEM
            )
            career = snap.get("career_name")
            competency = snap.get("competency_name")
            entity_key = str(career or competency or "unknown").lower()
            kw = user_prompt_keywords_block(
                career=str(career) if career else None,
                competency=str(competency) if competency else None,
            )
            pairs.append(
                {
                    "intent": intent,
                    "entity_key": entity_key,
                    "messages": [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": (
                                f"## Câu hỏi\n{user_msg.content}\n\n"
                                f"{kw}"
                                f"## Dữ liệu Neo4j\n"
                                f"{json.dumps(snap, ensure_ascii=False, indent=2)}"
                            ),
                        },
                        {"role": "assistant", "content": assistant.content},
                    ],
                    "meta": {
                        "source": "chat",
                        "message_id": assistant.id,
                        "session_id": str(assistant.session_id),
                        "intent": intent,
                        "entity_key": entity_key,
                    },
                }
            )
    return pairs


async def main_async(out_dir: Path, approved_only: bool) -> None:
    if not database_enabled():
        print("ERROR: DATABASE_URL required")
        sys.exit(1)

    pairs = await _load_pairs(approved_only=approved_only)
    by_intent: dict[str, list[dict]] = {i: [] for i in INTENTS}
    for p in pairs:
        by_intent.setdefault(p["intent"], []).append(p)

    for intent in INTENTS:
        items = by_intent[intent]
        train, val = split_by_entity(items)
        train_path, val_path = ft_paths(out_dir, intent)
        write_ft_jsonl(train_path, train)
        write_ft_jsonl(val_path, val)
        print(f"{intent}: train={len(train)} val={len(val)} -> {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "ft_from_chat",
        help="Snapshot export (merge vào data/ qua merge_ft_datasets.py)",
    )
    parser.add_argument(
        "--approved-only",
        action="store_true",
        help="Only export rows with review_status=approved",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.out_dir, args.approved_only))


if __name__ == "__main__":
    main()
