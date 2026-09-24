import os
from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def _get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set")
    return url


_async_engine = None
_async_session_maker = None
_sync_engine = None


def get_async_engine():
    global _async_engine

    if _async_engine is None:
        _async_engine = create_async_engine(
            _get_database_url(),
            echo=False,
            poolclass=NullPool,
        )

    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_maker

    if _async_session_maker is None:
        engine = get_async_engine()
        _async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    return _async_session_maker


def get_sync_engine():
    global _sync_engine

    if _sync_engine is None:
        sync_url = _get_database_url().replace("+asyncpg", "")
        _sync_engine = create_engine(sync_url, echo=False)

    return _sync_engine


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
