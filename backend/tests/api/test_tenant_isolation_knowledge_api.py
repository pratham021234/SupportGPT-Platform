"""API tests verifying multi-tenant isolation, cross-tenant denial, and direct-ID defense on knowledge assets."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.enums import (
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
    UserStatus,
)
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
async def tenant_isolation_context() -> AsyncIterator[
    tuple[AsyncClient, AsyncSession, Organization, Organization, User, User]
]:
    """Create test environment with two isolated organizations and their respective users."""
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

    async with session_factory() as db:
        # 1. Org Alpha & Org Beta
        org_a = Organization(name="Tenant Alpha", slug="tenant-alpha", status=OrganizationStatus.ACTIVE)
        org_b = Organization(name="Tenant Beta", slug="tenant-beta", status=OrganizationStatus.ACTIVE)
        db.add_all([org_a, org_b])
        await db.flush()

        # 2. Users
        pwd_hash = hash_password("TenantPass123!Safe")
        user_a = User(
            email="user_a@alpha.com",
            password_hash=pwd_hash,
            display_name="Alice Alpha",
            status=UserStatus.ACTIVE,
        )
        user_b = User(
            email="user_b@beta.com",
            password_hash=pwd_hash,
            display_name="Bob Beta",
            status=UserStatus.ACTIVE,
        )
        db.add_all([user_a, user_b])
        await db.flush()

        # 3. Memberships
        mem_a = OrganizationMembership(
            organization_id=org_a.id,
            user_id=user_a.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        mem_b = OrganizationMembership(
            organization_id=org_b.id,
            user_id=user_b.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        db.add_all([mem_a, mem_b])
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with session_factory() as db:
            yield client, db, org_a, org_b, user_a, user_b

    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client: AsyncClient, email: str, password: str = "TenantPass123!Safe") -> None:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_cross_tenant_knowledge_isolation(tenant_isolation_context):
    client, db, org_a, org_b, user_a, user_b = tenant_isolation_context

    # 1. User Alpha creates KB and uploads document under Org Alpha
    await login(client, user_a.email)

    res_kb_a = await client.post(
        f"/api/v1/organizations/{org_a.id}/knowledge-bases",
        json={"name": "Alpha Confidential Knowledge"},
    )
    assert res_kb_a.status_code == 201
    kb_a_id = res_kb_a.json()["id"]

    files = {"file": ("alpha_secret.txt", b"Alpha proprietary data", "text/plain")}
    res_upload_a = await client.post(
        f"/api/v1/organizations/{org_a.id}/knowledge-bases/{kb_a_id}/documents",
        files=files,
    )
    assert res_upload_a.status_code == 201
    doc_a_id = res_upload_a.json()["document"]["id"]

    # 2. User Beta logs in
    await login(client, user_b.email)

    # Cross-tenant organization URL access denied with 403
    res_cross_org = await client.get(f"/api/v1/organizations/{org_a.id}/knowledge-bases")
    assert res_cross_org.status_code == 403

    # Direct ID access within User Beta's own organization yields 404 (no existence disclosure)
    res_direct_kb = await client.get(f"/api/v1/organizations/{org_b.id}/knowledge-bases/{kb_a_id}")
    assert res_direct_kb.status_code == 404

    # Cannot upload to Alpha's KB via Beta's organization
    res_cross_upload = await client.post(
        f"/api/v1/organizations/{org_b.id}/knowledge-bases/{kb_a_id}/documents",
        files={"file": ("injected.txt", b"Malicious", "text/plain")},
    )
    assert res_cross_upload.status_code == 404

    # Cannot access Alpha's document
    res_cross_doc = await client.get(f"/api/v1/organizations/{org_b.id}/documents/{doc_a_id}")
    assert res_cross_doc.status_code == 404

    # Cannot access Alpha's document versions
    res_cross_ver = await client.get(f"/api/v1/organizations/{org_b.id}/documents/{doc_a_id}/versions")
    assert res_cross_ver.status_code == 404

    # Cannot access Alpha's chunks
    res_cross_chunks = await client.get(f"/api/v1/organizations/{org_b.id}/documents/{doc_a_id}/chunks")
    assert res_cross_chunks.status_code == 404

    # Cannot delete Alpha's document
    res_cross_del = await client.delete(f"/api/v1/organizations/{org_b.id}/documents/{doc_a_id}")
    assert res_cross_del.status_code == 404

    # Cannot reprocess Alpha's document
    res_cross_reprocess = await client.post(f"/api/v1/organizations/{org_b.id}/documents/{doc_a_id}/reprocess")
    assert res_cross_reprocess.status_code == 404
