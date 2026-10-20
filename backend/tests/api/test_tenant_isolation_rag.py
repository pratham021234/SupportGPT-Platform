"""Security tests for multi-tenant isolation, cross-tenant search prevention, and lifecycle filtering."""

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client import QdrantClient
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
from app.services.document_worker import DocumentWorker
from app.services.rag.embedding import FastEmbedEmbeddingProvider
from app.services.rag.qdrant_store import QdrantStoreManager


@pytest.fixture
def multi_tenant_qdrant_manager():
    """Shared in-memory Qdrant instance storing vectors for multiple tenants."""
    client = QdrantClient(location=":memory:")
    return QdrantStoreManager(
        collection_name="multi_tenant_rag_chunks",
        dimensions=384,
        client=client,
    )


@pytest.fixture
async def multi_tenant_rag_context(multi_tenant_qdrant_manager) -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], Organization, Organization, User, User, DocumentWorker, QdrantStoreManager]
]:
    """Test fixture with two completely disjoint organizations (Alpha and Beta)."""
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

    pwd = hash_password("Secret123!Safe")
    async with session_factory() as db:
        # Organization Alpha
        org_alpha = Organization(name="Alpha Corp", slug="alpha-corp", status=OrganizationStatus.ACTIVE)
        # Organization Beta
        org_beta = Organization(name="Beta Corp", slug="beta-corp", status=OrganizationStatus.ACTIVE)
        db.add_all([org_alpha, org_beta])
        await db.flush()

        # Users
        user_alpha = User(email="alice@alpha.com", password_hash=pwd, display_name="Alice Alpha", status=UserStatus.ACTIVE)
        user_beta = User(email="bob@beta.com", password_hash=pwd, display_name="Bob Beta", status=UserStatus.ACTIVE)
        db.add_all([user_alpha, user_beta])
        await db.flush()

        # Memberships
        mem_alpha = OrganizationMembership(
            organization_id=org_alpha.id, user_id=user_alpha.id, role=MembershipRole.ADMIN, status=MembershipStatus.ACTIVE
        )
        mem_beta = OrganizationMembership(
            organization_id=org_beta.id, user_id=user_beta.id, role=MembershipRole.ADMIN, status=MembershipStatus.ACTIVE
        )
        db.add_all([mem_alpha, mem_beta])
        await db.commit()

    embedding_provider = FastEmbedEmbeddingProvider(dimensions=384)
    worker = DocumentWorker(
        session_factory=session_factory,
        embedding_provider=embedding_provider,
        qdrant_store=multi_tenant_qdrant_manager,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, session_factory, org_alpha, org_beta, user_alpha, user_beta, worker, multi_tenant_qdrant_manager

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_knowledge_base_search_denied(multi_tenant_rag_context):
    """Verify an authenticated user from Organization Alpha cannot search Organization Beta's knowledge base."""
    client, session_factory, org_alpha, org_beta, user_alpha, user_beta, worker, qdrant_store = multi_tenant_rag_context

    # 1. Login as Alice (Alpha) and create KB in Alpha
    await client.post("/api/v1/auth/login", json={"email": "alice@alpha.com", "password": "Secret123!Safe"})
    kb_alpha_res = await client.post(
        f"/api/v1/organizations/{org_alpha.id}/knowledge-bases",
        json={"name": "Alpha Docs", "description": "Alpha KB"},
    )
    assert kb_alpha_res.status_code == 201
    _kb_alpha_id = kb_alpha_res.json()["id"]

    # 2. Login as Bob (Beta) and create KB in Beta
    await client.post("/api/v1/auth/login", json={"email": "bob@beta.com", "password": "Secret123!Safe"})
    kb_beta_res = await client.post(
        f"/api/v1/organizations/{org_beta.id}/knowledge-bases",
        json={"name": "Beta Docs", "description": "Beta KB"},
    )
    assert kb_beta_res.status_code == 201
    kb_beta_id = kb_beta_res.json()["id"]

    # 3. Alice (Alpha) logs back in
    await client.post("/api/v1/auth/login", json={"email": "alice@alpha.com", "password": "Secret123!Safe"})

    # Attempt direct ID access to Beta's KB under Alpha route
    with patch("app.services.rag.retrieval.get_qdrant_store", return_value=qdrant_store):
        cross_search_res = await client.post(
            f"/api/v1/organizations/{org_alpha.id}/knowledge-bases/{kb_beta_id}/search",
            json={"query": "test query"},
        )
        # MUST return 404 Not Found (knowledge base not found in organization)
        assert cross_search_res.status_code == 404

        # Attempt querying Beta's route directly
        cross_route_res = await client.post(
            f"/api/v1/organizations/{org_beta.id}/knowledge-bases/{kb_beta_id}/search",
            json={"query": "test query"},
        )
        # MUST return 403 Forbidden (not a member of Beta)
        assert cross_route_res.status_code == 403


@pytest.mark.asyncio
async def test_cross_tenant_vector_isolation(multi_tenant_rag_context):
    """Verify search vectors in a shared Qdrant collection never leak across tenant boundaries."""
    client, session_factory, org_alpha, org_beta, user_alpha, user_beta, worker, qdrant_store = multi_tenant_rag_context

    # 1. Login as Bob (Beta) and upload sensitive document
    await client.post("/api/v1/auth/login", json={"email": "bob@beta.com", "password": "Secret123!Safe"})
    kb_beta_res = await client.post(
        f"/api/v1/organizations/{org_beta.id}/knowledge-bases",
        json={"name": "Beta Confidential", "description": "Confidential"},
    )
    kb_beta_id = kb_beta_res.json()["id"]

    await client.post(
        f"/api/v1/organizations/{org_beta.id}/knowledge-bases/{kb_beta_id}/documents",
        files={"file": ("secret.txt", b"BETA CONFIDENTIAL PROJECT ZEUS SECRET KEY 998877", "text/plain")},
        data={"title": "Project Zeus"},
    )
    # Process Beta document into shared Qdrant store
    await worker.run_once()

    # 2. Login as Alice (Alpha) and upload different document
    await client.post("/api/v1/auth/login", json={"email": "alice@alpha.com", "password": "Secret123!Safe"})
    kb_alpha_res = await client.post(
        f"/api/v1/organizations/{org_alpha.id}/knowledge-bases",
        json={"name": "Alpha General", "description": "General"},
    )
    kb_alpha_id = kb_alpha_res.json()["id"]

    await client.post(
        f"/api/v1/organizations/{org_alpha.id}/knowledge-bases/{kb_alpha_id}/documents",
        files={"file": ("public.txt", b"Alpha organization public support hours 9am to 5pm", "text/plain")},
        data={"title": "Alpha Support"},
    )
    # Process Alpha document
    await worker.run_once()

    with patch("app.services.rag.retrieval.get_qdrant_store", return_value=qdrant_store):
        # Alice searches specifically for Beta's secret keyword "Project Zeus"
        alpha_search_res = await client.post(
            f"/api/v1/organizations/{org_alpha.id}/knowledge/search",
            json={"query": "Project Zeus secret key"},
        )
        assert alpha_search_res.status_code == 200
        alpha_data = alpha_search_res.json()

        # Alice MUST NOT retrieve Beta's chunk
        for ev in alpha_data["evidence"]:
            assert "ZEUS" not in ev["relevant_excerpt"]
            assert ev["knowledge_base_id"] != kb_beta_id

        # Bob (Beta) searching for "Project Zeus" finds his document
        await client.post("/api/v1/auth/login", json={"email": "bob@beta.com", "password": "Secret123!Safe"})
        beta_search_res = await client.post(
            f"/api/v1/organizations/{org_beta.id}/knowledge/search",
            json={"query": "Project Zeus secret key"},
        )
        assert beta_search_res.status_code == 200
        beta_data = beta_search_res.json()
        assert len(beta_data["evidence"]) >= 1
        assert "ZEUS" in beta_data["evidence"][0]["relevant_excerpt"]


@pytest.mark.asyncio
async def test_deleted_document_excluded_from_retrieval(multi_tenant_rag_context):
    """Verify soft-deleted documents immediately disappear from retrieval candidates."""
    client, session_factory, org_alpha, org_beta, user_alpha, user_beta, worker, qdrant_store = multi_tenant_rag_context

    await client.post("/api/v1/auth/login", json={"email": "alice@alpha.com", "password": "Secret123!Safe"})
    kb_res = await client.post(
        f"/api/v1/organizations/{org_alpha.id}/knowledge-bases",
        json={"name": "Alpha Docs", "description": "Docs"},
    )
    kb_id = kb_res.json()["id"]

    upload_res = await client.post(
        f"/api/v1/organizations/{org_alpha.id}/knowledge-bases/{kb_id}/documents",
        files={"file": ("doc.txt", b"Temporary deprecation notice for legacy API v1", "text/plain")},
        data={"title": "Deprecation Notice"},
    )
    doc_id = upload_res.json()["document"]["id"]
    await worker.run_once()

    with patch("app.services.rag.retrieval.get_qdrant_store", return_value=qdrant_store), \
         patch("app.services.document_service.get_qdrant_store", return_value=qdrant_store):
        # 1. Search before deletion finds document
        res_before = await client.post(
            f"/api/v1/organizations/{org_alpha.id}/knowledge/search",
            json={"query": "legacy API v1 deprecation"},
        )
        assert res_before.status_code == 200
        assert len(res_before.json()["evidence"]) >= 1

        # 2. Soft delete document
        del_res = await client.delete(
            f"/api/v1/organizations/{org_alpha.id}/documents/{doc_id}",
        )
        assert del_res.status_code == 200

        # 3. Search after deletion returns 0 results
        res_after = await client.post(
            f"/api/v1/organizations/{org_alpha.id}/knowledge/search",
            json={"query": "legacy API v1 deprecation"},
        )
        assert res_after.status_code == 200
        assert len(res_after.json()["evidence"]) == 0
