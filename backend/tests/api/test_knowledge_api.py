"""API integration tests for knowledge bases, document uploads, revisions, RBAC, and lifecycle."""

import uuid
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
async def knowledge_test_context() -> AsyncIterator[
    tuple[AsyncClient, AsyncSession, Organization, User, User, User]
]:
    """Create test environment with organization, Admin user, Agent user, and Viewer user."""
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
        # 1. Organization
        org = Organization(
            name="SupportGPT Corp", slug="supportgpt-corp", status=OrganizationStatus.ACTIVE
        )
        db.add(org)
        await db.flush()

        # 2. Users
        pwd_hash = hash_password("Secret123!Safe")
        admin_user = User(
            email="admin@supportgpt.com",
            password_hash=pwd_hash,
            display_name="Admin Alice",
            status=UserStatus.ACTIVE,
        )
        agent_user = User(
            email="agent@supportgpt.com",
            password_hash=pwd_hash,
            display_name="Agent Bob",
            status=UserStatus.ACTIVE,
        )
        viewer_user = User(
            email="viewer@supportgpt.com",
            password_hash=pwd_hash,
            display_name="Viewer Charlie",
            status=UserStatus.ACTIVE,
        )
        db.add_all([admin_user, agent_user, viewer_user])
        await db.flush()

        # 3. Memberships
        admin_mem = OrganizationMembership(
            organization_id=org.id,
            user_id=admin_user.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        agent_mem = OrganizationMembership(
            organization_id=org.id,
            user_id=agent_user.id,
            role=MembershipRole.AGENT,
            status=MembershipStatus.ACTIVE,
        )
        viewer_mem = OrganizationMembership(
            organization_id=org.id,
            user_id=viewer_user.id,
            role=MembershipRole.VIEWER,
            status=MembershipStatus.ACTIVE,
        )
        db.add_all([admin_mem, agent_mem, viewer_mem])
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with session_factory() as db:
            yield client, db, org, admin_user, agent_user, viewer_user

    app.dependency_overrides.clear()
    await engine.dispose()


async def login_as(client: AsyncClient, email: str, password: str = "Secret123!Safe") -> None:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_knowledge_base_crud_and_conflict(knowledge_test_context):
    client, db, org, admin_user, _, _ = knowledge_test_context
    await login_as(client, admin_user.email)

    # 1. Create Knowledge Base
    res = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge-bases",
        json={"name": "Engineering Runbooks", "description": "SRE and Developer Runbooks"},
    )
    assert res.status_code == 201
    kb_data = res.json()
    assert kb_data["name"] == "Engineering Runbooks"
    assert kb_data["status"] == "active"
    kb_id = kb_data["id"]

    # 2. Duplicate name returns 409 Conflict
    res_dup = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge-bases",
        json={"name": "Engineering Runbooks"},
    )
    assert res_dup.status_code == 409

    # 3. List Knowledge Bases
    res_list = await client.get(f"/api/v1/organizations/{org.id}/knowledge-bases")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["total"] >= 1
    assert any(k["id"] == kb_id for k in list_data["items"])

    # 4. Get Knowledge Base by ID
    res_get = await client.get(f"/api/v1/organizations/{org.id}/knowledge-bases/{kb_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == kb_id


@pytest.mark.asyncio
async def test_document_upload_and_lifecycle(knowledge_test_context):
    client, db, org, admin_user, agent_user, _ = knowledge_test_context
    await login_as(client, agent_user.email)

    # Create KB
    res_kb = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge-bases",
        json={"name": "Customer Support FAQ"},
    )
    kb_id = res_kb.json()["id"]

    # 1. Upload Markdown Document
    md_content = b"# Password Reset Guide\n\nUsers can reset their password via settings."
    files = {"file": ("password_reset.md", md_content, "text/markdown")}
    data = {"title": "Password Reset Procedures"}

    res_upload = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge-bases/{kb_id}/documents",
        files=files,
        data=data,
    )
    assert res_upload.status_code == 201
    upload_res = res_upload.json()
    doc = upload_res["document"]
    ver = upload_res["version"]

    assert doc["title"] == "Password Reset Procedures"
    assert doc["media_type"] == "text/markdown"
    assert doc["current_version_number"] == 1
    assert ver["version_number"] == 1
    assert ver["processing_status"] == "queued"

    doc_id = doc["id"]

    # 2. Get Document by ID
    res_doc = await client.get(f"/api/v1/organizations/{org.id}/documents/{doc_id}")
    assert res_doc.status_code == 200
    assert res_doc.json()["id"] == doc_id

    # 3. List Versions
    res_vers = await client.get(f"/api/v1/organizations/{org.id}/documents/{doc_id}/versions")
    assert res_vers.status_code == 200
    assert len(res_vers.json()) == 1

    # 4. Upload New Version (v2)
    v2_content = b"# Password Reset Guide v2\n\nAdded 2FA authentication steps."
    v2_files = {"file": ("password_reset_v2.md", v2_content, "text/markdown")}

    res_v2 = await client.post(
        f"/api/v1/organizations/{org.id}/documents/{doc_id}/versions",
        files=v2_files,
    )
    assert res_v2.status_code == 201
    v2_data = res_v2.json()
    assert v2_data["version_number"] == 2
    assert v2_data["processing_status"] == "queued"

    # Prior version reference is still active in parent document until worker publishes v2
    doc_after_v2 = (await client.get(f"/api/v1/organizations/{org.id}/documents/{doc_id}")).json()
    assert doc_after_v2["current_version_number"] == 1

    # 5. Reprocess Version
    res_reprocess = await client.post(
        f"/api/v1/organizations/{org.id}/documents/{doc_id}/reprocess"
    )
    assert res_reprocess.status_code == 200
    assert res_reprocess.json()["processing_status"] == "queued"

    # 6. Soft Delete Document (Admin)
    await login_as(client, admin_user.email)
    res_del = await client.delete(f"/api/v1/organizations/{org.id}/documents/{doc_id}")
    assert res_del.status_code == 200
    assert res_del.json()["lifecycle_status"] == "deleted"

    # Deleted document no longer appears in active list
    res_list = await client.get(f"/api/v1/organizations/{org.id}/documents")
    assert all(d["id"] != doc_id for d in res_list.json()["items"])


@pytest.mark.asyncio
async def test_rbac_knowledge_permissions(knowledge_test_context):
    client, db, org, _, _, viewer_user = knowledge_test_context
    await login_as(client, viewer_user.email)

    # Viewer role cannot create knowledge base
    res_kb = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge-bases",
        json={"name": "Forbidden KB"},
    )
    assert res_kb.status_code == 403

    # Viewer role cannot upload documents
    fake_kb_id = uuid.uuid4()
    files = {"file": ("test.txt", b"Hello", "text/plain")}
    res_upload = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge-bases/{fake_kb_id}/documents",
        files=files,
    )
    assert res_upload.status_code == 403

    # Viewer role cannot delete documents
    fake_doc_id = uuid.uuid4()
    res_del = await client.delete(f"/api/v1/organizations/{org.id}/documents/{fake_doc_id}")
    assert res_del.status_code == 403
