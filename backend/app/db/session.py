"""Asynchronous database engine configuration, session management, and connectivity verification."""

import time
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("supportgpt.db")


def create_engine_instance() -> AsyncEngine:
    """Instantiate async database engine with production pool configuration."""
    return create_async_engine(
        settings.async_database_url,
        echo=settings.DEBUG,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,  # Test connection viability before handing out of pool
    )


async_engine: AsyncEngine = create_engine_instance()

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an isolated async database session with transaction management."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def verify_database_connection(
    timeout_seconds: float = 3.0,
) -> tuple[bool, float, str | None]:
    """Execute a lightweight probe query to verify database liveness and measure round-trip latency.

    Returns:
        tuple[is_connected, latency_ms, error_message]
    """
    start = time.perf_counter()
    try:
        async with async_engine.connect() as conn:
            # Enforce light query timeout
            await conn.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - start) * 1000
        return True, round(latency_ms, 2), None
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.error(f"Database health probe failed after {latency_ms:.1f}ms: {exc}")
        return False, round(latency_ms, 2), str(exc)
