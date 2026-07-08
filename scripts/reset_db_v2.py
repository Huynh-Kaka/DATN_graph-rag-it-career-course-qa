"""
Xóa schema chat cũ và tạo lại v2 (user_profiles tách khỏi chat_sessions).

Chạy: python scripts/reset_db_v2.py
Cần: DATABASE_URL trong .env và PostgreSQL đang chạy.
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

    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.engine import database_enabled, get_engine

    if not database_enabled():
        print("ERROR: DATABASE_URL chưa được cấu hình trong .env")
        sys.exit(1)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS message_feedback CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS advice_results CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS chat_messages CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS chat_sessions CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS user_profiles CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS user_background CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS target_role CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS weekly_time CASCADE"))
        await conn.execute(text("DROP TYPE IF EXISTS review_status CASCADE"))
        await conn.run_sync(Base.metadata.create_all)

    print("OK: Database reset to schema v2 (SQLAlchemy metadata).")
    print(
        "Tables: user_profiles, chat_sessions, chat_messages, "
        "message_feedback, advice_results"
    )


if __name__ == "__main__":
    asyncio.run(main())
