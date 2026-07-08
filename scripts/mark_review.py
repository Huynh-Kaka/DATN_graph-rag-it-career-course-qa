"""
Human review CLI for message_feedback.

Chạy:
  python scripts/mark_review.py list-pending
  python scripts/mark_review.py approve --feedback-id 1 --reviewer expert1
  python scripts/mark_review.py reject --feedback-id 2 --reviewer expert1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.db.enums import ReviewStatus
from app.db.feedback_repository import FeedbackRepository
from app.db.engine import database_enabled


async def list_pending() -> None:
    repo = FeedbackRepository()
    rows = await repo.list_pending_review(limit=50)
    if not rows:
        print("(empty)")
        return
    for r in rows:
        print(
            f"id={r['id']} message_id={r['message_id']} rating={r['rating']} "
            f"comment={r['comment']!r}"
        )


async def set_status(feedback_id: int, status: ReviewStatus, reviewer: str) -> None:
    repo = FeedbackRepository()
    row = await repo.update_review_status(
        feedback_id=feedback_id,
        review_status=status,
        reviewer=reviewer,
    )
    print(row)


def main() -> None:
    if not database_enabled():
        print("ERROR: DATABASE_URL required")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-pending")

    for name, status in (
        ("approve", ReviewStatus.approved),
        ("reject", ReviewStatus.rejected),
    ):
        p = sub.add_parser(name)
        p.add_argument("--feedback-id", type=int, required=True)
        p.add_argument("--reviewer", type=str, default="expert")

    args = parser.parse_args()
    if args.cmd == "list-pending":
        asyncio.run(list_pending())
    elif args.cmd == "approve":
        asyncio.run(set_status(args.feedback_id, ReviewStatus.approved, args.reviewer))
    elif args.cmd == "reject":
        asyncio.run(set_status(args.feedback_id, ReviewStatus.rejected, args.reviewer))


if __name__ == "__main__":
    main()
