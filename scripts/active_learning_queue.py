"""
Export messages for expert labeling (low confidence or negative feedback).

Chạy: python scripts/active_learning_queue.py --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from sqlalchemy import select

from app.db.engine import database_enabled, session_scope
from app.db.models import ChatMessageModel, MessageFeedbackModel


async def build_queue(limit: int) -> list[dict]:
    queue: list[dict] = []
    async with session_scope() as db:
        stmt = (
            select(ChatMessageModel, MessageFeedbackModel)
            .outerjoin(
                MessageFeedbackModel,
                MessageFeedbackModel.message_id == ChatMessageModel.id,
            )
            .where(ChatMessageModel.role == "assistant")
            .order_by(ChatMessageModel.id.desc())
            .limit(500)
        )
        rows = (await db.execute(stmt)).all()
        for msg, fb in rows:
            route = msg.route or {}
            conf = route.get("confidence") if isinstance(route, dict) else None
            snap = route.get("graph_snapshot") if isinstance(route, dict) else {}
            found = isinstance(snap, dict) and snap.get("found")
            negative = fb is not None and fb.rating == -1
            low_conf = conf == "low" or (isinstance(snap, dict) and not found)
            if negative or low_conf:
                queue.append(
                    {
                        "message_id": msg.id,
                        "session_id": str(msg.session_id),
                        "intent": msg.intent,
                        "content_preview": (msg.content or "")[:200],
                        "rating": fb.rating if fb else None,
                        "reason": "negative_feedback" if negative else "low_confidence",
                    }
                )
            if len(queue) >= limit:
                break
    return queue


def main() -> None:
    if not database_enabled():
        print("ERROR: DATABASE_URL required")
        sys.exit(1)
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "data" / "active_learning_queue.json")
    args = parser.parse_args()

    queue = asyncio.run(build_queue(args.limit))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(queue)} items to {args.out}")


if __name__ == "__main__":
    main()
