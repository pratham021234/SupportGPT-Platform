"""Database integration tests validating live PostgreSQL connection and schema metadata."""

import pytest

import app.models  # Ensure all models are registered in Base.metadata # noqa: F401
from app.db.base import Base
from app.db.session import verify_database_connection


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


def test_base_metadata_contains_all_canonical_domain_tables():
    """Verify that SQLAlchemy declarative registry contains all authoritative domain and foundation tables."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {
        "organizations",
        "organization_ticket_counters",
        "customers",
        "customer_identities",
        "tickets",
        "conversations",
        "messages",
        "attachments",
        "ticket_events",
        "ingestion_receipts",
        "system_event_logs",
        "users",
        "organization_memberships",
        "user_sessions",
    }
    assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"


def test_tenant_boundary_composite_foreign_keys_configured():
    """Verify that child entities enforce tenant boundary consistency via composite foreign keys."""
    # 1. Conversations must reference Tickets via (ticket_id, organization_id)
    conv_table = Base.metadata.tables["conversations"]
    conv_fks = [[col.name for col in fk.columns] for fk in conv_table.foreign_key_constraints]
    assert ["ticket_id", "organization_id"] in conv_fks or [
        "organization_id",
        "ticket_id",
    ] in conv_fks

    # 2. Messages must reference Conversations via (conversation_id, organization_id)
    msg_table = Base.metadata.tables["messages"]
    msg_fks = [[col.name for col in fk.columns] for fk in msg_table.foreign_key_constraints]
    assert ["conversation_id", "organization_id"] in msg_fks or [
        "organization_id",
        "conversation_id",
    ] in msg_fks

    # 3. Attachments must reference Messages via (message_id, organization_id)
    att_table = Base.metadata.tables["attachments"]
    att_fks = [[col.name for col in fk.columns] for fk in att_table.foreign_key_constraints]
    assert ["message_id", "organization_id"] in att_fks or [
        "organization_id",
        "message_id",
    ] in att_fks

    # 4. TicketEvents must reference Tickets via (ticket_id, organization_id)
    event_table = Base.metadata.tables["ticket_events"]
    event_fks = [[col.name for col in fk.columns] for fk in event_table.foreign_key_constraints]
    assert ["ticket_id", "organization_id"] in event_fks or [
        "organization_id",
        "ticket_id",
    ] in event_fks
