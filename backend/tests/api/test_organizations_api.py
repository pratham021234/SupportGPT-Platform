"""API integration tests for organization membership management and RBAC rules."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import generate_session_token, hash_password, hash_session_token
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.enums import MembershipRole, MembershipStatus, OrganizationStatus, UserStatus
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.session import UserSession
from app.models.user import User


@pytest.fixture
async def org_test_env() -> AsyncIterator[dict]:
    """Setup isolated in-memory database with organizations and multi-role users."""
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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with session_factory() as db:
            # 1. Create Organization Alpha
            org_alpha = Organization(name="Alpha Corp", slug="alpha-corp", status=OrganizationStatus.ACTIVE)
            db.add(org_alpha)

            # 2. Create Users
            owner_user = User(
                email="owner@alpha.io",
                password_hash=hash_password("Pass123!"),
                display_name="Alpha Owner",
                status=UserStatus.ACTIVE,
            )
            admin_user = User(
                email="admin@alpha.io",
                password_hash=hash_password("Pass123!"),
                display_name="Alpha Admin",
                status=UserStatus.ACTIVE,
            )
            agent_user = User(
                email="agent@alpha.io",
                password_hash=hash_password("Pass123!"),
                display_name="Alpha Agent",
                status=UserStatus.ACTIVE,
            )
            viewer_user = User(
                email="viewer@alpha.io",
                password_hash=hash_password("Pass123!"),
                display_name="Alpha Viewer",
                status=UserStatus.ACTIVE,
            )
            db.add_all([owner_user, admin_user, agent_user, viewer_user])
            await db.flush()

            # 3. Create Memberships
            m_owner = OrganizationMembership(
                organization_id=org_alpha.id,
                user_id=owner_user.id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
            m_admin = OrganizationMembership(
                organization_id=org_alpha.id,
                user_id=admin_user.id,
                role=MembershipRole.ADMIN,
                status=MembershipStatus.ACTIVE,
            )
            m_agent = OrganizationMembership(
                organization_id=org_alpha.id,
                user_id=agent_user.id,
                role=MembershipRole.AGENT,
                status=MembershipStatus.ACTIVE,
            )
            m_viewer = OrganizationMembership(
                organization_id=org_alpha.id,
                user_id=viewer_user.id,
                role=MembershipRole.VIEWER,
                status=MembershipStatus.ACTIVE,
            )
            db.add_all([m_owner, m_admin, m_agent, m_viewer])

            # 4. Create active sessions and tokens
            tokens = {}
            for role_name, u in [
                ("owner", owner_user),
                ("admin", admin_user),
                ("agent", agent_user),
                ("viewer", viewer_user),
            ]:
                raw_token = generate_session_token()
                tokens[role_name] = raw_token
                sess = UserSession(
                    user_id=u.id,
                    session_token_hash=hash_session_token(raw_token),
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                )
                db.add(sess)

            await db.commit()

            yield {
                "client": client,
                "db": db,
                "org": org_alpha,
                "tokens": tokens,
                "memberships": {
                    "owner": m_owner,
                    "admin": m_admin,
                    "agent": m_agent,
                    "viewer": m_viewer,
                },
                "users": {
                    "owner": owner_user,
                    "admin": admin_user,
                    "agent": agent_user,
                    "viewer": viewer_user,
                },
            }

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_my_membership_permissions(org_test_env: dict):
    """Verify caller can inspect their membership and permissions in target organization."""
    client = org_test_env["client"]
    org = org_test_env["org"]
    token = org_test_env["tokens"]["agent"]

    response = await client.get(
        f"/api/v1/organizations/{org.id}/memberships/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "agent"
    assert "tickets:read" in data["permissions"]
    assert "tickets:write" in data["permissions"]
    assert "org:members:manage" not in data["permissions"]


@pytest.mark.asyncio
async def test_list_members_requires_permission(org_test_env: dict):
    """Verify listing members is allowed for Admin/Owner and forbidden for Agent/Viewer."""
    client = org_test_env["client"]
    org = org_test_env["org"]

    # 1. Admin succeeds
    admin_res = await client.get(
        f"/api/v1/organizations/{org.id}/members",
        headers={"Authorization": f"Bearer {org_test_env['tokens']['admin']}"},
    )
    assert admin_res.status_code == 200
    assert len(admin_res.json()) == 4

    # 2. Agent is rejected with 403 Forbidden
    agent_res = await client.get(
        f"/api/v1/organizations/{org.id}/members",
        headers={"Authorization": f"Bearer {org_test_env['tokens']['agent']}"},
    )
    assert agent_res.status_code == 403
    assert agent_res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_admin_cannot_escalate_to_owner(org_test_env: dict):
    """Verify that an ADMIN attempting to provision an OWNER role is blocked (privilege escalation prevention)."""
    client = org_test_env["client"]
    org = org_test_env["org"]
    admin_token = org_test_env["tokens"]["admin"]

    # Admin attempts to add an Owner
    response = await client.post(
        f"/api/v1/organizations/{org.id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "hacker@evil.com",
            "display_name": "Hacker",
            "role": "owner",
        },
    )
    assert response.status_code == 403
    assert "not authorized to assign the privileged 'owner' role" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_owner_can_add_member(org_test_env: dict):
    """Verify OWNER can add a new member with any role."""
    client = org_test_env["client"]
    org = org_test_env["org"]
    owner_token = org_test_env["tokens"]["owner"]

    response = await client.post(
        f"/api/v1/organizations/{org.id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "email": "newbie@alpha.io",
            "display_name": "Newbie Agent",
            "role": "agent",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newbie@alpha.io"
    assert data["role"] == "agent"


@pytest.mark.asyncio
async def test_last_owner_demotion_protection(org_test_env: dict):
    """Verify that demoting the sole active owner is strictly prevented."""
    client = org_test_env["client"]
    org = org_test_env["org"]
    owner_token = org_test_env["tokens"]["owner"]
    owner_membership = org_test_env["memberships"]["owner"]

    # Owner attempts to demote self to agent
    response = await client.patch(
        f"/api/v1/organizations/{org.id}/members/{owner_membership.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"role": "agent"},
    )
    assert response.status_code == 403
    assert "Cannot demote the last remaining active owner" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_last_owner_removal_protection(org_test_env: dict):
    """Verify that revoking the sole active owner is strictly prevented."""
    client = org_test_env["client"]
    org = org_test_env["org"]
    owner_token = org_test_env["tokens"]["owner"]
    owner_membership = org_test_env["memberships"]["owner"]

    response = await client.delete(
        f"/api/v1/organizations/{org.id}/members/{owner_membership.id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert response.status_code == 403
    assert "Cannot remove the last remaining active owner" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_admin_cannot_demote_owner(org_test_env: dict):
    """Verify that an ADMIN cannot modify or demote an OWNER."""
    client = org_test_env["client"]
    org = org_test_env["org"]
    admin_token = org_test_env["tokens"]["admin"]
    owner_membership = org_test_env["memberships"]["owner"]

    response = await client.patch(
        f"/api/v1/organizations/{org.id}/members/{owner_membership.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "agent"},
    )
    assert response.status_code == 403
    assert "not authorized to modify a member with role 'owner'" in response.json()["error"]["message"]
