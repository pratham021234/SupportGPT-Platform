"""Coordinated database migration runner with PostgreSQL advisory locking.

Prevents multi-replica race conditions during concurrent container deployments.
"""

import asyncio
import os
import sys

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("supportgpt.migrations")

# Deterministic 64-bit integer advisory lock key for SupportGPT Alembic migrations
MIGRATION_ADVISORY_LOCK_ID = 847291038


async def run_coordinated_migrations() -> None:
    """Run Alembic migrations with an advisory lock in PostgreSQL."""
    db_url = settings.async_database_url
    logger.info("Initiating coordinated database migration against %s", settings.ENVIRONMENT)

    # For PostgreSQL databases, acquire an advisory lock to prevent concurrent migration execution
    is_postgres = "postgresql" in db_url
    engine = None

    if is_postgres:
        engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")
        async with engine.connect() as conn:
            logger.info("Acquiring PostgreSQL advisory lock %d...", MIGRATION_ADVISORY_LOCK_ID)
            await conn.execute(text(f"SELECT pg_advisory_lock({MIGRATION_ADVISORY_LOCK_ID});"))
            logger.info("Advisory lock acquired. Executing Alembic upgrade head...")

            try:
                # Run synchronous alembic command in thread
                await asyncio.to_thread(_run_alembic_upgrade)
                logger.info("Database migrations completed successfully.")
            finally:
                logger.info("Releasing PostgreSQL advisory lock %d...", MIGRATION_ADVISORY_LOCK_ID)
                await conn.execute(
                    text(f"SELECT pg_advisory_unlock({MIGRATION_ADVISORY_LOCK_ID});")
                )
                await engine.dispose()
    else:
        # SQLite / in-memory mode
        logger.info("Non-PostgreSQL datastore detected. Executing direct Alembic upgrade...")
        await asyncio.to_thread(_run_alembic_upgrade)
        logger.info("Database migrations completed.")


def _run_alembic_upgrade() -> None:
    """Execute Alembic upgrade head synchronously."""
    # Find alembic.ini relative to project root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ini_path = os.path.join(base_dir, "alembic.ini")
    alembic_cfg = Config(ini_path)
    command.upgrade(alembic_cfg, "head")


def main() -> None:
    """CLI entrypoint."""
    try:
        asyncio.run(run_coordinated_migrations())
    except Exception as exc:
        logger.exception("Migration execution failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
