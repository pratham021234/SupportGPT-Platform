"""API tests for operational receipt queries, replay workflows, and worker diagnostics."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password, hash_session_token
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.enums import (
    IngestionStatus,
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
    UserStatus,
)
from app.models.ingestion_receipt import IngestionReceipt
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.session import UserSession
from app.models.user import User


@pytest.fixture
async def ingestion_api_context() -> AsyncIterator[
    tuple[AsyncClient, AsyncSession, Organization, User, User, User, str, str, str]
]:
    """Setup test context with Admin, Agent, and Viewer users."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    app = create_application()

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_get_db_session

    admin_token = "admin_ingest_token_12345"
    agent_token = "agent_ingest_token_12345"
    viewer_token = "viewer_ingest_token_12345"

    async with session_factory() as db:
        org = Organization(name="Ops Org", slug="ops-org", status=OrganizationStatus.ACTIVE)
        db.add(org)
        await db.flush()

        pwd = hash_password("SecurePass123!")
        admin = User(
            email="admin@ops.com", password_hash=pwd, display_name="Admin", status=UserStatus.ACTIVE
        )
        agent = User(
            email="agent@ops.com", password_hash=pwd, display_name="Agent", status=UserStatus.ACTIVE
        )
        viewer = User(
            email="viewer@ops.com",
            password_hash=pwd,
            display_name="Viewer",
            status=UserStatus.ACTIVE,
        )
        db.add_all([admin, agent, viewer])
        await db.flush()

        m_admin = OrganizationMembership(
            organization_id=org.id,
            user_id=admin.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        m_agent = OrganizationMembership(
            organization_id=org.id,
            user_id=agent.id,
            role=MembershipRole.AGENT,
            status=MembershipStatus.ACTIVE,
        )
        m_viewer = OrganizationMembership(
            organization_id=org.id,
            user_id=viewer.id,
            role=MembershipRole.VIEWER,
            status=MembershipStatus.ACTIVE,
        )
        db.add_all([m_admin, m_agent, m_viewer])

        from datetime import timedelta

        expires = datetime.now(UTC) + timedelta(days=7)
        s_admin = UserSession(
            user_id=admin.id, session_token_hash=hash_session_token(admin_token), expires_at=expires
        )
        s_agent = UserSession(
            user_id=agent.id, session_token_hash=hash_session_token(agent_token), expires_at=expires
        )
        s_viewer = UserSession(
            user_id=viewer.id,
            session_token_hash=hash_session_token(viewer_token),
            expires_at=expires,
        )
        db.add_all([s_admin, s_agent, s_viewer])

        # Seed sample receipts
        now = datetime.now(UTC)
        r1 = IngestionReceipt(
            organization_id=org.id,
            source_provider="generic_webhook",
            external_event_id="evt-rec-1",
            event_type="ticket.created",
            status=IngestionStatus.PROCESSED,
            received_at=now,
            payload={"subject": "Processed Event"},
        )
        r2 = IngestionReceipt(
            organization_id=org.id,
            source_provider="generic_webhook",
            external_event_id="evt-rec-2",
            event_type="ticket.created",
            status=IngestionStatus.DEAD_LETTER,
            received_at=now,
            attempt_count=5,
            error_code="MAX_ATTEMPTS_EXCEEDED",
            error_summary="Failed to connect to upstream service",
            payload={"subject": "Failed Event"},
        )
        db.add_all([r1, r2])
        await db.commit()
        await db.refresh(org)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db, org, admin, agent, viewer, admin_token, agent_token, viewer_token

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_receipts_with_status_filter(ingestion_api_context):
    """Listing receipts supports filtering by status and pagination."""
    client, _, org, _, _, _, admin_token, _, _ = ingestion_api_context
    headers = {"Authorization": f"Bearer {admin_token}"}

    # All receipts
    res_all = await client.get(
        f"/api/v1/organizations/{org.id}/ingestion/receipts", headers=headers
    )
    assert res_all.status_code == 200
    assert res_all.json()["total"] == 2

    # Filtered by dead_letter
    res_dl = await client.get(
        f"/api/v1/organizations/{org.id}/ingestion/receipts?status=dead_letter",
        headers=headers,
    )
    assert res_dl.status_code == 200
    assert res_dl.json()["total"] == 1
    assert res_dl.json()["items"][0]["status"] == "dead_letter"
    assert res_dl.json()["items"][0]["error_code"] == "MAX_ATTEMPTS_EXCEEDED"


@pytest.mark.asyncio
async def test_get_receipt_detail(ingestion_api_context):
    """Receipt detail endpoint returns payload and error summary."""
    client, _, org, _, _, _, admin_token, _, _ = ingestion_api_context
    headers = {"Authorization": f"Bearer {admin_token}"}

    list_res = await client.get(
        f"/api/v1/organizations/{org.id}/ingestion/receipts", headers=headers
    )
    receipt_id = list_res.json()["items"][0]["id"]

    detail_res = await client.get(
        f"/api/v1/organizations/{org.id}/ingestion/receipts/{receipt_id}",
        headers=headers,
    )
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert data["id"] == receipt_id
    assert "payload" in data


@pytest.mark.asyncio
async def test_replay_dead_lettered_receipt(ingestion_api_context):
    """Replaying a dead-lettered receipt resets status to QUEUED and attempts to 0."""
    client, _, org, _, _, _, admin_token, _, _ = ingestion_api_context
    headers = {"Authorization": f"Bearer {admin_token}"}

    dl_res = await client.get(
        f"/api/v1/organizations/{org.id}/ingestion/receipts?status=dead_letter",
        headers=headers,
    )
    receipt_id = dl_res.json()["items"][0]["id"]

    # Replay
    replay_res = await client.post(
        f"/api/v1/organizations/{org.id}/ingestion/receipts/{receipt_id}/replay",
        headers=headers,
    )
    assert replay_res.status_code == 200
    data = replay_res.json()
    assert data["status"] == "queued"
    assert data["attempt_count"] == 0
    assert data["error_code"] is None


@pytest.mark.asyncio
async def test_replay_processed_receipt_conflict(ingestion_api_context):
    """Replaying a successful receipt without force=True triggers 409 Conflict."""
    client, _, org, _, _, _, admin_token, _, _ = ingestion_api_context
    headers = {"Authorization": f"Bearer {admin_token}"}

    p_res = await client.get(
        f"/api/v1/organizations/{org.id}/ingestion/receipts?status=processed",
        headers=headers,
    )
    receipt_id = p_res.json()["items"][0]["id"]

    # Replay without force
    replay_res = await client.post(
        f"/api/v1/organizations/{org.id}/ingestion/receipts/{receipt_id}/replay",
        json={"force": False},
        headers=headers,
    )
    assert replay_res.status_code == 409
    assert replay_res.json()["error"]["code"] == "RECEIPT_NOT_REPLAYABLE"


@pytest.mark.asyncio
async def test_ingestion_rbac_enforcement(ingestion_api_context):
    """Viewer is forbidden from receipts, Agent can view, Admin can replay."""
    client, _, org, _, _, _, admin_token, agent_token, viewer_token = ingestion_api_context
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    agent_headers = {"Authorization": f"Bearer {agent_token}"}

    # Viewer denied
    v_res = await client.get(
        f"/api/v1/organizations/{org.id}/ingestion/receipts", headers=viewer_headers
    )
    assert v_res.status_code == 403

    # Agent allowed to read
    a_res = await client.get(
        f"/api/v1/organizations/{org.id}/ingestion/receipts", headers=agent_headers
    )
    assert a_res.status_code == 200

    # Agent forbidden from replay (requires ingestion:manage)
    receipt_id = a_res.json()["items"][0]["id"]
    a_replay = await client.post(
        f"/api/v1/organizations/{org.id}/ingestion/receipts/{receipt_id}/replay",
        headers=agent_headers,
    )
    assert a_replay.status_code == 403


@pytest.mark.asyncio
async def test_worker_health_diagnostics_endpoint(ingestion_api_context):
    """Worker diagnostics endpoint returns queue depth and health metrics."""
    client, _, _, _, _, _, _, _, _ = ingestion_api_context

    health_res = await client.get("/api/v1/ingestion/worker/health")
    assert health_res.status_code == 200
    data = health_res.json()
    assert "status" in data
    assert "queue_depth" in data
    assert "dead_letter_count" in data
    assert "lease_timeout_seconds" in data
