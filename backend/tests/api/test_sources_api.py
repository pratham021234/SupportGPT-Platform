"""API tests for external source configuration, secret rotation, and RBAC."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password, hash_session_token
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.enums import MembershipRole, MembershipStatus, OrganizationStatus, UserStatus
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.session import UserSession
from app.models.user import User


@pytest.fixture
async def sources_context() -> AsyncIterator[
    tuple[AsyncClient, AsyncSession, Organization, User, User, str, str]
]:
    """Setup environment with an organization, an admin user, an agent user, and active sessions."""
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

    admin_token = "admin_session_token_1234567890abcdef"
    agent_token = "agent_session_token_1234567890abcdef"

    async with session_factory() as db:
        org = Organization(
            name="Sources Test Org", slug="sources-org", status=OrganizationStatus.ACTIVE
        )
        db.add(org)
        await db.flush()

        pwd = hash_password("Pass123!Secure")
        admin = User(
            email="admin@sources.com",
            password_hash=pwd,
            display_name="Admin Alice",
            status=UserStatus.ACTIVE,
        )
        agent = User(
            email="agent@sources.com",
            password_hash=pwd,
            display_name="Agent Bob",
            status=UserStatus.ACTIVE,
        )
        db.add_all([admin, agent])
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
        db.add_all([m_admin, m_agent])
        await db.flush()

        from datetime import UTC, datetime, timedelta

        expires = datetime.now(UTC) + timedelta(days=7)
        s_admin = UserSession(
            user_id=admin.id, session_token_hash=hash_session_token(admin_token), expires_at=expires
        )
        s_agent = UserSession(
            user_id=agent.id, session_token_hash=hash_session_token(agent_token), expires_at=expires
        )
        db.add_all([s_admin, s_agent])
        await db.commit()
        await db.refresh(org)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db, org, admin, agent, admin_token, agent_token

    await engine.dispose()


@pytest.mark.asyncio
async def test_source_creation_and_secret_revelation(sources_context):
    """Creating a source returns the raw secret once, and stores preview and hash."""
    client, _, org, _, _, admin_token, _ = sources_context

    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "name": "Acme SendGrid Webhook",
        "provider": "email_sendgrid",
        "supported_event_types": ["ticket.created", "message.received"],
    }

    res = await client.post(
        f"/api/v1/organizations/{org.id}/sources", json=payload, headers=headers
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Acme SendGrid Webhook"
    assert data["provider"] == "email_sendgrid"
    assert data["status"] == "active"
    assert "secret_value" in data
    assert data["secret_value"].startswith("whsec_")
    assert "signing_secret_preview" in data
    assert data["signing_secret_preview"].startswith("whsec_")

    source_id = data["id"]

    # In subsequent GET request, secret_value is NOT present
    get_res = await client.get(
        f"/api/v1/organizations/{org.id}/sources/{source_id}", headers=headers
    )
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert "secret_value" not in get_data
    assert get_data["signing_secret_preview"] == data["signing_secret_preview"]


@pytest.mark.asyncio
async def test_source_listing_and_filtering(sources_context):
    """Listing sources returns all sources for the organization without exposing secrets."""
    client, _, org, _, _, admin_token, _ = sources_context
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Create two sources
    await client.post(
        f"/api/v1/organizations/{org.id}/sources",
        json={"name": "Source A", "provider": "generic_webhook"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/organizations/{org.id}/sources",
        json={"name": "Source B", "provider": "custom_api"},
        headers=headers,
    )

    list_res = await client.get(f"/api/v1/organizations/{org.id}/sources", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    for item in data["items"]:
        assert "secret_value" not in item
        assert "signing_secret_preview" in item


@pytest.mark.asyncio
async def test_source_update_properties(sources_context):
    """Updating source modifies name and status successfully."""
    client, _, org, _, _, admin_token, _ = sources_context
    headers = {"Authorization": f"Bearer {admin_token}"}

    create_res = await client.post(
        f"/api/v1/organizations/{org.id}/sources",
        json={"name": "Initial Name", "provider": "generic_webhook"},
        headers=headers,
    )
    source_id = create_res.json()["id"]

    update_payload = {"name": "Updated Name", "status": "inactive"}
    patch_res = await client.patch(
        f"/api/v1/organizations/{org.id}/sources/{source_id}",
        json=update_payload,
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Updated Name"
    assert patch_res.json()["status"] == "inactive"


@pytest.mark.asyncio
async def test_secret_rotation(sources_context):
    """Rotating secret generates new secret value once and updates preview."""
    client, _, org, _, _, admin_token, _ = sources_context
    headers = {"Authorization": f"Bearer {admin_token}"}

    create_res = await client.post(
        f"/api/v1/organizations/{org.id}/sources",
        json={"name": "Rotate Target", "provider": "generic_webhook"},
        headers=headers,
    )
    source_id = create_res.json()["id"]
    old_secret = create_res.json()["secret_value"]
    old_preview = create_res.json()["signing_secret_preview"]

    rotate_res = await client.post(
        f"/api/v1/organizations/{org.id}/sources/{source_id}/rotate-secret",
        headers=headers,
    )
    assert rotate_res.status_code == 200
    new_data = rotate_res.json()
    assert new_data["secret_value"] != old_secret
    assert new_data["signing_secret_preview"] != old_preview


@pytest.mark.asyncio
async def test_source_management_rbac_enforcement(sources_context):
    """Agent can read sources but is forbidden from creating, updating, or rotating secrets."""
    client, _, org, _, _, admin_token, agent_token = sources_context
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    agent_headers = {"Authorization": f"Bearer {agent_token}"}

    # 1. Admin creates source
    c_res = await client.post(
        f"/api/v1/organizations/{org.id}/sources",
        json={"name": "Admin Source", "provider": "generic_webhook"},
        headers=admin_headers,
    )
    source_id = c_res.json()["id"]

    # 2. Agent can read sources (sources:read)
    list_res = await client.get(f"/api/v1/organizations/{org.id}/sources", headers=agent_headers)
    assert list_res.status_code == 200

    # 3. Agent is forbidden from creating sources (requires sources:manage)
    agent_create = await client.post(
        f"/api/v1/organizations/{org.id}/sources",
        json={"name": "Agent Source", "provider": "generic_webhook"},
        headers=agent_headers,
    )
    assert agent_create.status_code == 403

    # 4. Agent is forbidden from rotating secret
    agent_rotate = await client.post(
        f"/api/v1/organizations/{org.id}/sources/{source_id}/rotate-secret",
        headers=agent_headers,
    )
    assert agent_rotate.status_code == 403
