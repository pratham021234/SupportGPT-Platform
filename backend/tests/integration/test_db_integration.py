"""Database integration tests validating live PostgreSQL connection and schema metadata."""

import pytest

from app.db.base import Base
from app.db.session import verify_database_connection
from app.models.foundation import SystemEventLog


@pytest.mark.asyncio
async def test_live_database_connection_probe():
    """Verify live PostgreSQL database connectivity.

    If the PostgreSQL container is not running, the test reports as BLOCKED (skipped with explanation)
    rather than falsely passing.
    """
    is_connected, latency_ms, error = await verify_database_connection(timeout_seconds=2.0)
    if not is_connected:
        pytest.skip(
            f"Database integration test BLOCKED: PostgreSQL service is unreachable ({error}). "
            "Start PostgreSQL via 'docker compose up -d postgres' to execute live database tests."
        )

    assert is_connected is True
    assert latency_ms > 0


def test_base_metadata_contains_foundational_models():
    """Verify that SQLAlchemy declarative registry contains authoritative foundation tables."""
    table_names = list(Base.metadata.tables.keys())
    assert SystemEventLog.__tablename__ in table_names

    # Check constraint and index naming conventions
    table = Base.metadata.tables["system_event_logs"]
    assert "id" in table.columns
    assert "event_name" in table.columns
    assert "created_at" in table.columns
    assert "updated_at" in table.columns
