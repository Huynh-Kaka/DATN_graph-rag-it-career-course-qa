from __future__ import annotations

import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.base import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Tham số query libpq (sslmode, channel_binding) không hợp lệ với asyncpg.
_LIBPQ_ONLY_QUERY_KEYS = frozenset({"sslmode", "channel_binding"})


def _prepare_asyncpg_url(url: str) -> tuple[str, dict]:
    parsed = urlparse(url)
    if not parsed.query:
        connect_args: dict = {}
        if parsed.hostname and parsed.hostname.endswith(".neon.tech"):
            connect_args["ssl"] = ssl.create_default_context()
        return url, connect_args

    qs = parse_qs(parsed.query)
    connect_args = {}
    sslmode = (qs.pop("sslmode", [""])[0] or "").lower()
    for key in _LIBPQ_ONLY_QUERY_KEYS:
        qs.pop(key, None)
    if sslmode in ("require", "verify-ca", "verify-full", "prefer", "allow"):
        connect_args["ssl"] = ssl.create_default_context()
    elif parsed.hostname and parsed.hostname.endswith(".neon.tech"):
        connect_args["ssl"] = ssl.create_default_context()

    flat = {k: v[-1] for k, v in qs.items() if v}
    clean = urlunparse(parsed._replace(query=urlencode(flat)))
    return clean, connect_args


def database_enabled() -> bool:
    return bool(settings.database_url)


def get_engine() -> AsyncEngine:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL chưa được cấu hình.")
    global _engine
    if _engine is None:
        db_url, connect_args = _prepare_asyncpg_url(settings.database_url)
        _engine = create_async_engine(
            db_url,
            echo=settings.database_echo,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_database() -> None:
    if not database_enabled():
        return
    import logging

    logger = logging.getLogger(__name__)
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL tables ready (asyncpg).")
    except Exception as exc:
        logger.warning(
            "Không kết nối PostgreSQL (%s). Đặt DATABASE_URL= để dùng session in-memory.",
            exc,
        )


async def close_database() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
