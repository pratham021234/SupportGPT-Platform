"""API integration tests for Knowledge Search and Grounded Question Answering."""

from collections.abc import AsyncIterator

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
from app.services.document_service import DocumentService
from app.services.document_worker import DocumentWorker
from app.services.rag.embedding import FastEmbedEmbeddingProvider
from app.services.rag.qdrant_store import QdrantStoreManager


@pytest.fixture
def test_qdrant_manager():
    """In-memory Qdrant instance for test isolation."""
    client = QdrantClient(location=":memory:")
    return QdrantStoreManager(
        collection_name="test_rag_api_chunks",
        dimensions=384,
        client=client,
    )


@pytest.fixture
async def rag_api_context(
    test_qdrant_manager,
) -> AsyncIterator[
    tuple[
        AsyncClient,
        async_sessionmaker[AsyncSession],
        Organization,
        User,
        User,
        DocumentService,
        DocumentWorker,
        QdrantStoreManager,
    ]
]:
    """Test fixture with an active organization, users, and pre-indexed knowledge base."""
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
        org = Organization(name="SaaS Corp", slug="saas-corp", status=OrganizationStatus.ACTIVE)
        db.add(org)
        await db.flush()

        pwd = hash_password("Pass123!Safe")
        admin = User(
            email="admin@saas.com",
            password_hash=pwd,
            display_name="Admin",
            status=UserStatus.ACTIVE,
        )
        agent = User(
            email="agent@saas.com",
            password_hash=pwd,
            display_name="Agent",
            status=UserStatus.ACTIVE,
        )
        db.add_all([admin, agent])
        await db.flush()

        mem_admin = OrganizationMembership(
            organization_id=org.id,
            user_id=admin.id,
            role=MembershipRole.ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        mem_agent = OrganizationMembership(
            organization_id=org.id,
            user_id=agent.id,
            role=MembershipRole.AGENT,
            status=MembershipStatus.ACTIVE,
        )
        db.add_all([mem_admin, mem_agent])
        await db.commit()

    embedding_provider = FastEmbedEmbeddingProvider(dimensions=384)
    worker = DocumentWorker(
        session_factory=session_factory,
        embedding_provider=embedding_provider,
        qdrant_store=test_qdrant_manager,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with session_factory() as db:
            doc_service = DocumentService(db)
            yield (
                client,
                session_factory,
                org,
                admin,
                agent,
                doc_service,
                worker,
                test_qdrant_manager,
            )

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_and_grounded_answer_api(rag_api_context):
    """Verify search returns ranked evidence and answer endpoint generates grounded response with citations."""
    client, session_factory, org, admin, agent, doc_service, worker, qdrant_store = rag_api_context

    # 1. Login as Admin
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@saas.com", "password": "Pass123!Safe"},
    )
    assert login_res.status_code == 200

    # 2. Create Knowledge Base and Upload Policy Document
    kb_res = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge-bases",
        json={"name": "Internal Security", "description": "Security policies"},
    )
    assert kb_res.status_code == 201
    kb_id = kb_res.json()["id"]

    policy_content = (
        b"# Corporate Security Policy\n\n"
        b"## Password Controls\n"
        b"All user accounts require a minimum password length of 16 characters. "
        b"Passwords must include alphanumeric and special characters.\n\n"
        b"## Session Controls\n"
        b"All idle administrative sessions will terminate automatically after 15 minutes of inactivity."
    )

    upload_res = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge-bases/{kb_id}/documents",
        files={"file": ("security_policy.md", policy_content, "text/markdown")},
        data={"title": "Corporate Security Policy"},
    )
    assert upload_res.status_code == 201

    # 3. Background Worker Processes & Indexes Document into Qdrant
    processed = await worker.run_once()
    assert processed == 1

    # Override QdrantStoreManager in RetrievalService to use our test in-memory instance
    from unittest.mock import patch

    with patch("app.services.rag.retrieval.get_qdrant_store", return_value=qdrant_store):
        # 4. Search Endpoint
        search_res = await client.post(
            f"/api/v1/organizations/{org.id}/knowledge-bases/{kb_id}/search",
            json={"query": "minimum password length", "top_k": 3},
        )
        assert search_res.status_code == 200
        search_data = search_res.json()
        assert search_data["query"] == "minimum password length"
        assert search_data["total_results"] >= 1
        assert len(search_data["evidence"]) >= 1
        assert "16 characters" in search_data["evidence"][0]["relevant_excerpt"]
        assert search_data["evidence"][0]["citation_reference"] == "[citation:1]"
        assert search_data["retrieval_latency_ms"] >= 0.0

        # 5. Answer Endpoint (Grounded Answer)
        answer_res = await client.post(
            f"/api/v1/organizations/{org.id}/knowledge-bases/{kb_id}/answer",
            json={"question": "What is the minimum password length requirement?"},
        )
        assert answer_res.status_code == 200
        answer_data = answer_res.json()
        assert answer_data["abstention_status"] is False
        assert "16 characters" in answer_data["answer"]
        assert "[citation:1]" in answer_data["answer"]
        assert len(answer_data["citations"]) >= 1
        assert answer_data["citations"][0]["citation_number"] == 1
        assert answer_data["citations"][0]["source_title"] == "Corporate Security Policy"

        # 6. Answer Endpoint (Abstention on Out-of-Domain Question)
        abstain_res = await client.post(
            f"/api/v1/organizations/{org.id}/knowledge-bases/{kb_id}/answer",
            json={"question": "What is the recipe for chocolate chip cookies?"},
        )
        assert abstain_res.status_code == 200
        abstain_data = abstain_res.json()
        assert abstain_data["abstention_status"] is True
        assert len(abstain_data["citations"]) == 0

        # 7. Organization-Wide Search
        org_search_res = await client.post(
            f"/api/v1/organizations/{org.id}/knowledge/search",
            json={"query": "session termination timeout", "top_k": 3},
        )
        assert org_search_res.status_code == 200
        assert len(org_search_res.json()["evidence"]) >= 1
        assert "15 minutes" in org_search_res.json()["evidence"][0]["relevant_excerpt"]


@pytest.mark.asyncio
async def test_search_query_validation(rag_api_context):
    """Verify search endpoint rejects invalid or empty query strings."""
    client, session_factory, org, admin, agent, doc_service, worker, qdrant_store = rag_api_context

    await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@saas.com", "password": "Pass123!Safe"},
    )
    # Single character query (< 2 characters)
    res_short = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge/search",
        json={"query": "a"},
    )
    assert res_short.status_code == 422 or res_short.status_code == 400

    # Oversized query (> 2000 characters)
    res_long = await client.post(
        f"/api/v1/organizations/{org.id}/knowledge/search",
        json={"query": "x" * 2005},
    )
    assert res_long.status_code == 422 or res_long.status_code == 400
