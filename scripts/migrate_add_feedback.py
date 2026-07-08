"""
Thêm bảng message_feedback và enum review_status (không xóa dữ liệu chat).

Chạy: python scripts/migrate_add_feedback.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)


async def main() -> None:
    from sqlalchemy import text

    from app.db.engine import database_enabled, get_engine

    if not database_enabled():
        print("ERROR: DATABASE_URL chưa được cấu hình")
        sys.exit(1)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DO $$ BEGIN
                  CREATE TYPE review_status AS ENUM ('pending', 'approved', 'rejected');
                EXCEPTION
                  WHEN duplicate_object THEN NULL;
                END $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS message_feedback (
                  id             bigserial PRIMARY KEY,
                  message_id     bigint NOT NULL UNIQUE
                                 REFERENCES chat_messages(id) ON DELETE CASCADE,
                  rating         integer NOT NULL CHECK (rating IN (-1, 1)),
                  comment        text,
                  review_status  review_status NOT NULL DEFAULT 'pending',
                  reviewer       varchar(128),
                  created_at     timestamptz NOT NULL DEFAULT now(),
                  updated_at     timestamptz NOT NULL DEFAULT now()
                );
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_message_feedback_review_status
                ON message_feedback(review_status);
                """
            )
        )

    print("OK: message_feedback ready.")


if __name__ == "__main__":
    asyncio.run(main())
