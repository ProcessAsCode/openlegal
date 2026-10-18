"""Async database engine, session factory, and FastAPI dependency.

The application uses one engine per process. The session factory yields short-lived
`AsyncSession` instances bound to that engine. Endpoints depend on `get_session`
to receive a request-scoped session — committed on success, rolled back on exception,
always closed when the request finishes.

Tests can swap the engine via `set_engine_for_testing` so a throwaway Postgres
container can be used without touching this module's defaults.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from openlegal.core.config import settings

if TYPE_CHECKING:
    from fastapi import FastAPI


# ---------------------------------------------------------------------------
# Engine + session factory (lazy, process-wide)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first call."""
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(
            settings.DB_URL,
            pool_pre_ping=True,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            echo=False,
        )
        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the current engine."""
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None  # appeases type checkers
    return _session_factory


def set_engine_for_testing(engine: AsyncEngine) -> None:
    """Swap the engine + session factory for tests."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False
    )


async def dispose_engine() -> None:
    """Close the engine's pool. Called on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session.

    On clean exit: commit (so endpoint handlers don't need to commit explicitly
    for happy-path writes). On exception: rollback. Always close.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Same semantics as `get_session` but usable outside FastAPI handlers
    (e.g. from background tasks, CLI helpers, tests).
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
