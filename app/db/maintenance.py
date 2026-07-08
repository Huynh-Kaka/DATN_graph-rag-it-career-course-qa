"""Tiện ích bảo trì PostgreSQL — xóa dữ liệu, giữ nguyên schema."""

from __future__ import annotations

from sqlalchemy import text

from app.db.engine import database_enabled, get_engine

_APP_TABLES: tuple[str, ...] = (
    "message_feedback",
    "advice_results",
    "chat_messages",
    "chat_sessions",
    "user_profiles",
)


async def count_postgres_rows() -> dict[str, int]:
    """Đếm số dòng từng bảng ứng dụng."""
    if not database_enabled():
        raise RuntimeError("DATABASE_URL chưa được cấu hình.")
    engine = get_engine()
    counts: dict[str, int] = {}
    async with engine.connect() as conn:
        for table in _APP_TABLES:
            result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = int(result.scalar_one())
    return counts


async def clear_all_postgres_data() -> dict[str, int]:
    """
    Xóa toàn bộ dữ liệu chat/profile/tư vấn trong PostgreSQL.

    Giữ nguyên schema, enum types và sequence (reset về 1).
    Trả về số dòng đã xóa theo từng bảng (đếm trước khi truncate).
    """
    if not database_enabled():
        raise RuntimeError("DATABASE_URL chưa được cấu hình.")

    counts = await count_postgres_rows()
    tables_sql = ", ".join(_APP_TABLES)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {tables_sql} RESTART IDENTITY CASCADE")
        )
    return counts
