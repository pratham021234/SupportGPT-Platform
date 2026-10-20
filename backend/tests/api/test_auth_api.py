"""API integration tests for authentication, sessions, and credential security."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.enums import MembershipRole, MembershipStatus, OrganizationStatus, UserStatus
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
async def auth_test_context() -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    """Isolated in-memory SQLite database and test client with overridden session dependency."""
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
            yield client, db

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_login_successful_and_cookie_issued(
    auth_test_context: tuple[AsyncClient, AsyncSession],
):
    """Verify login succeeds with valid credentials, setting HttpOnly cookie and returning sanitized profile."""
    client, db = auth_test_context

    # 1. Seed user and organization
    org = Organization(name="Acme Corp", slug="acme-corp", status=OrganizationStatus.ACTIVE)
    db.add(org)
    await db.flush()

    user = User(
        email="operator@acmecorp.io",
        password_hash=hash_password("SuperSecret123!"),
        display_name="Acme Operator",
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.flush()

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=user.id,
        role=MembershipRole.OWNER,
        status=MembershipStatus.ACTIVE,
    )
    db.add(membership)
    await db.commit()

    # 2. Execute login request
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "operator@acmecorp.io", "password": "SuperSecret123!"},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify user profile data
    assert data["user"]["email"] == "operator@acmecorp.io"
    assert data["user"]["display_name"] == "Acme Operator"
    assert data["user"]["status"] == "active"

    # Verify NO password hash or secrets in response
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]

    # Verify organizations list
    assert len(data["organizations"]) == 1
    assert data["organizations"][0]["name"] == "Acme Corp"
    assert data["organizations"][0]["role"] == "owner"

    # Verify session cookie was set
    cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
    assert cookie is not None


@pytest.mark.asyncio
async def test_login_invalid_password(auth_test_context: tuple[AsyncClient, AsyncSession]):
    """Verify that an incorrect password returns 401 with generic error message."""
    client, db = auth_test_context

    user = User(
        email="agent@example.com",
        password_hash=hash_password("CorrectPassword123!"),
        display_name="Support Agent",
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "agent@example.com", "password": "WrongPassword999!"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "AUTHENTICATION_FAILED"
    assert payload["error"]["message"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_login_nonexistent_user_returns_generic_error(
    auth_test_context: tuple[AsyncClient, AsyncSession],
):
    """Verify that non-existent users receive the exact same error message to prevent email enumeration."""
    client, _ = auth_test_context

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.com", "password": "AnyPassword123!"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["message"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_login_disabled_account_denied(auth_test_context: tuple[AsyncClient, AsyncSession]):
    """Verify that disabled accounts cannot log in even with correct credentials."""
    client, db = auth_test_context

    user = User(
        email="banned@example.com",
        password_hash=hash_password("ValidPassword123!"),
        display_name="Banned User",
        status=UserStatus.DISABLED,
    )
    db.add(user)
    await db.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "banned@example.com", "password": "ValidPassword123!"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert "inactive or disabled" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_logout_and_session_invalidation(auth_test_context: tuple[AsyncClient, AsyncSession]):
    """Verify logout revokes the server session and prevents subsequent access."""
    client, db = auth_test_context

    user = User(
        email="logout_test@example.com",
        password_hash=hash_password("ValidPass123!"),
        display_name="Logout Tester",
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()

    # 1. Login
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "logout_test@example.com", "password": "ValidPass123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]

    # 2. Access /me with token
    me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200

    # 3. Logout
    logout_res = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout_res.status_code == 200

    # 4. Attempt to access /me after logout
    post_logout_res = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert post_logout_res.status_code == 401
