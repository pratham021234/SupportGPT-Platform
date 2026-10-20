"""Security tests verifying multi-tenant boundary defense and direct-ID attack resistance for sources and ingestion."""

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
    SourceProvider,
    SourceStatus,
    UserStatus,
)
from app.models.event_source import EventSource
from app.models.ingestion_receipt import IngestionReceipt
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.session import UserSession
from app.models.user import User


@pytest.fixture
async def multi_tenant_context() -> AsyncIterator[
    tuple[
        AsyncClient,
        AsyncSession,
        Organization,
        Organization,
        EventSource,
        IngestionReceipt,
        str,
        str,
    ]
]:
    """Setup Org A (victim) and Org B (attacker) with distinct sources, receipts, and sessions."""
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

    org_a_token = "org_a_admin_token_abcdef123456"
    org_b_token = "org_b_admin_token_abcdef123456"

    async with session_factory() as db:
        org_a = Organization(
            name="Tenant Alpha", slug="tenant-alpha", status=OrganizationStatus.ACTIVE
        )
        org_b = Organization(
            name="Tenant Beta", slug="tenant-beta", status=OrganizationStatus.ACTIVE
        )
        db.add_all([org_a, org_b])
        await db.flush()

        pwd = hash_password("Pass123!Secure")
        user_a = User(
            email="admin@alpha.com",
            password_hash=pwd,
            display_name="Alpha Admin",
            status=UserStatus.ACTIVE,
        )
        user_b = User(
            email="admin@beta.com",
            password_hash=pwd,
            display_name="Beta Admin",
            status=UserStatus.ACTIVE,
        )
        db.add_all([user_a, user_b])
        await db.flush()

        m_a = OrganizationMembership(
            organization_id=org_a.id,
            user_id=user_a.id,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        m_b = OrganizationMembership(
            organization_id=org_b.id,
            user_id=user_b.id,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        db.add_all([m_a, m_b])

        from datetime import timedelta

        expires = datetime.now(UTC) + timedelta(days=7)
        s_a = UserSession(
            user_id=user_a.id,
            session_token_hash=hash_session_token(org_a_token),
            expires_at=expires,
        )
        s_b = UserSession(
            user_id=user_b.id,
            session_token_hash=hash_session_token(org_b_token),
            expires_at=expires,
        )
        db.add_all([s_a, s_b])

        # Org A resources
        src_a = EventSource(
            organization_id=org_a.id,
            name="Org A Private Source",
            provider=SourceProvider.GENERIC_WEBHOOK,
            status=SourceStatus.ACTIVE,
            signing_secret_hash="hash_a",
            signing_secret_preview="whsec_a...1234",
        )
        db.add(src_a)
        await db.flush()

        rec_a = IngestionReceipt(
            organization_id=org_a.id,
            source_id=src_a.id,
            source_provider=SourceProvider.GENERIC_WEBHOOK,
            external_event_id="evt-alpha-private",
            event_type="ticket.created",
            status=IngestionStatus.DEAD_LETTER,
            received_at=datetime.now(UTC),
            payload={"secret_data": "alpha_customer_info"},
        )
        db.add(rec_a)
        await db.commit()
        await db.refresh(src_a)
        await db.refresh(rec_a)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db, org_a, org_b, src_a, rec_a, org_a_token, org_b_token

    await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_source_read_returns_404(multi_tenant_context):
    """Tenant B attempting to read Tenant A's event source by UUID receives 404 Not Found."""
    client, _, org_a, org_b, src_a, _, _, org_b_token = multi_tenant_context
    headers_b = {"Authorization": f"Bearer {org_b_token}"}

    # Attack: Org B asks for Org A's source within Org B's URL
    res = await client.get(
        f"/api/v1/organizations/{org_b.id}/sources/{src_a.id}",
        headers=headers_b,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_tenant_source_update_returns_404(multi_tenant_context):
    """Tenant B attempting to update Tenant A's event source receives 404 Not Found."""
    client, _, _, org_b, src_a, _, _, org_b_token = multi_tenant_context
    headers_b = {"Authorization": f"Bearer {org_b_token}"}

    res = await client.patch(
        f"/api/v1/organizations/{org_b.id}/sources/{src_a.id}",
        json={"name": "Tampered by Beta"},
        headers=headers_b,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_tenant_source_secret_rotation_returns_404(multi_tenant_context):
    """Tenant B attempting to rotate Tenant A's signing secret receives 404 Not Found."""
    client, _, _, org_b, src_a, _, _, org_b_token = multi_tenant_context
    headers_b = {"Authorization": f"Bearer {org_b_token}"}

    res = await client.post(
        f"/api/v1/organizations/{org_b.id}/sources/{src_a.id}/rotate-secret",
        headers=headers_b,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_tenant_receipt_read_returns_404(multi_tenant_context):
    """Tenant B attempting to read Tenant A's ingestion receipt receives 404 Not Found."""
    client, _, _, org_b, _, rec_a, _, org_b_token = multi_tenant_context
    headers_b = {"Authorization": f"Bearer {org_b_token}"}

    res = await client.get(
        f"/api/v1/organizations/{org_b.id}/ingestion/receipts/{rec_a.id}",
        headers=headers_b,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_tenant_receipt_replay_returns_404(multi_tenant_context):
    """Tenant B attempting to replay Tenant A's dead-letter receipt receives 404 Not Found."""
    client, _, _, org_b, _, rec_a, _, org_b_token = multi_tenant_context
    headers_b = {"Authorization": f"Bearer {org_b_token}"}

    res = await client.post(
        f"/api/v1/organizations/{org_b.id}/ingestion/receipts/{rec_a.id}/replay",
        headers=headers_b,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
