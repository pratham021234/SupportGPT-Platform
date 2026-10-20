"""Integration tests running RAG retrieval and Qdrant indexing against live PostgreSQL 16."""

import os
import uuid

import pytest
from qdrant_client import QdrantClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentProcessingStatus, KnowledgeBaseStatus, OrganizationStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.organization import Organization
from app.services.document_service import DocumentService
from app.services.document_worker import DocumentWorker
from app.services.rag.answer import GroundedAnswerService
from app.services.rag.embedding import FastEmbedEmbeddingProvider
from app.services.rag.qdrant_store import QdrantStoreManager
from app.services.rag.retrieval import RetrievalService

POSTGRES_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://supportgpt_user:supportgpt_dev_password@localhost:5432/supportgpt_test_db",
)


@pytest.fixture
async def live_postgres_rag_env():
    """Fixture providing a live PostgreSQL connection and clean test organization."""
    engine = create_async_engine(POSTGRES_TEST_URL, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Live PostgreSQL not reachable at {POSTGRES_TEST_URL}: {exc}")

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    org_id = uuid.uuid4()
    kb_id = uuid.uuid4()

    async with session_factory() as session:
        org = Organization(
            id=org_id,
            name=f"Live RAG Org {org_id.hex[:6]}",
            slug=f"live-rag-org-{org_id.hex[:6]}",
            status=OrganizationStatus.ACTIVE,
        )
        session.add(org)
        await session.commit()

    async with session_factory() as session:
        await session.execute(text(f"SELECT set_config('app.current_organization_id', '{org_id}', false)"))
        kb = KnowledgeBase(
            id=kb_id,
            organization_id=org_id,
            name="Live SLA Documentation",
            status=KnowledgeBaseStatus.ACTIVE,
        )
        session.add(kb)
        await session.commit()

    # Use in-memory Qdrant client for test isolation
    qdrant_manager = QdrantStoreManager(
        collection_name="live_postgres_rag_chunks",
        dimensions=384,
        client=QdrantClient(location=":memory:"),
    )
    embedding_provider = FastEmbedEmbeddingProvider(dimensions=384)

    worker = DocumentWorker(
        session_factory=session_factory,
        embedding_provider=embedding_provider,
        qdrant_store=qdrant_manager,
    )

    yield session_factory, org_id, kb_id, worker, qdrant_manager, embedding_provider

    # Teardown in reverse relational dependency order
    async with session_factory() as session:
        await session.execute(text("SELECT set_config('app.is_system_admin', 'true', false)"))
        await session.execute(delete(DocumentChunk).where(DocumentChunk.organization_id == org_id))
        await session.execute(delete(DocumentVersion).where(DocumentVersion.organization_id == org_id))
        await session.execute(delete(Document).where(Document.organization_id == org_id))
        await session.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
        await session.execute(delete(Organization).where(Organization.id == org_id))
        await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_live_postgres_rag_pipeline(live_postgres_rag_env):
    """Verify live PostgreSQL full-text search, Qdrant indexing, and grounded answering."""
    session_factory, org_id, kb_id, worker, qdrant_manager, embedding_provider = live_postgres_rag_env

    doc_text = (
        b"# Enterprise Customer SLA Terms\n\n"
        b"## Priority 1 Critical Incidents\n"
        b"Critical Severity 1 incidents have an initial response time target of 15 minutes. "
        b"Support engineers are dispatched 24/7/365 for critical service outages.\n\n"
        b"## Priority 2 Major Degradation\n"
        b"Major Severity 2 degradation events have an initial response time target of 2 hours.\n\n"
        b"## Refund Window Policy\n"
        b"Customers may request a billing refund within 30 days of invoice generation."
    )

    # 1. Upload Document into Live PostgreSQL
    async with session_factory() as session:
        await session.execute(text(f"SELECT set_config('app.current_organization_id', '{org_id}', true)"))
        service = DocumentService(session)
        doc, ver = await service.upload_document(
            organization_id=org_id,
            knowledge_base_id=kb_id,
            filename="sla_policy.md",
            content_bytes=doc_text,
            title="Enterprise Customer SLA Terms",
        )
        doc_id = doc.id
        ver_id = ver.id

    # 2. Worker executes extraction, chunking, real FastEmbed embeddings, and Qdrant upsert
    processed = await worker.run_once()
    assert processed == 1

    # 3. Verify Version and Document are INDEXED in PostgreSQL
    async with session_factory() as session:
        await session.execute(text(f"SELECT set_config('app.current_organization_id', '{org_id}', true)"))
        version = (await session.execute(select(DocumentVersion).where(DocumentVersion.id == ver_id))).scalar_one()
        assert version.processing_status == DocumentProcessingStatus.INDEXED
        assert version.chunk_count >= 2

        document = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one()
        assert document.status == DocumentProcessingStatus.INDEXED
        assert document.current_version_id == ver_id

    # 4. Authoritative Retrieval on Live PostgreSQL with Hybrid Search
    async with session_factory() as session:
        await session.execute(text(f"SELECT set_config('app.current_organization_id', '{org_id}', true)"))
        retrieval = RetrievalService(
            session=session,
            embedding_provider=embedding_provider,
            qdrant_store=qdrant_manager,
        )

        # Query testing exact SLA keyword match + semantic similarity
        evidence, latency_ms = await retrieval.retrieve(
            query="What is the response time for Priority 1 Critical incidents?",
            organization_id=org_id,
            knowledge_base_ids=[kb_id],
            top_k=3,
            enable_hybrid=True,
        )

        assert len(evidence) >= 1
        top_ev = evidence[0]
        assert "15 minutes" in top_ev.relevant_excerpt
        assert top_ev.source_title == "Enterprise Customer SLA Terms"
        assert top_ev.citation_reference == "[citation:1]"
        assert latency_ms > 0.0

        # 5. Generate Grounded Answer
        answer_service = GroundedAnswerService()
        result = await answer_service.generate_answer(
            question="What is the response time for Priority 1 Critical incidents?",
            evidence=evidence,
            retrieval_latency_ms=latency_ms,
        )

        assert result.abstention_status is False
        assert "15 minutes" in result.answer
        assert "[citation:1]" in result.answer
        assert len(result.citations) >= 1
        assert result.citations[0].citation_number == 1

        # 6. Verify Abstention on Unrelated Query
        unrelated_evidence, _ = await retrieval.retrieve(
            query="What is the stock price of Apple Inc?",
            organization_id=org_id,
            knowledge_base_ids=[kb_id],
            top_k=3,
        )
        # Even if low similarity chunks return, answer service must abstain
        unrelated_result = await answer_service.generate_answer(
            question="What is the stock price of Apple Inc?",
            evidence=unrelated_evidence,
        )
        assert unrelated_result.abstention_status is True
        assert len(unrelated_result.citations) == 0
