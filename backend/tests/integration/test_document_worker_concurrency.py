"""Integration tests for DocumentWorker: pipeline execution, lease reclamation, concurrency, and version safety."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentProcessingStatus, KnowledgeBaseStatus, OrganizationStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.organization import Organization
from app.services.document_service import DocumentService
from app.services.document_worker import DocumentWorker


@pytest.fixture
async def worker_test_env():
    """Create test environment for worker concurrency testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        org = Organization(name="Worker Test Org", slug="worker-test-org", status=OrganizationStatus.ACTIVE)
        session.add(org)
        await session.flush()

        kb = KnowledgeBase(
            organization_id=org.id,
            name="Platform Documentation",
            status=KnowledgeBaseStatus.ACTIVE,
        )
        session.add(kb)
        await session.commit()
        await session.refresh(org)
        await session.refresh(kb)

    yield session_factory, org, kb

    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_end_to_end_pipeline(worker_test_env):
    session_factory, org, kb = worker_test_env

    # 1. Upload a markdown document
    md_content = (
        b"# SupportGPT Operations Guide\n\n"
        b"This guide covers operations and incident escalation.\n\n"
        b"## Incident Severity Levels\n\n"
        b"P1: Outage affecting all users.\n\n"
        b"P2: Degraded performance."
    )

    async with session_factory() as session:
        service = DocumentService(session)
        doc, ver = await service.upload_document(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            filename="operations.md",
            content_bytes=md_content,
        )
        doc_id = doc.id
        ver_id = ver.id

    # 2. Run worker cycle
    worker = DocumentWorker(session_factory=session_factory, worker_id="test-worker-1")
    processed_count = await worker.run_once()
    assert processed_count == 1

    # 3. Verify version and chunks
    async with session_factory() as session:
        ver_res = await session.execute(select(DocumentVersion).where(DocumentVersion.id == ver_id))
        version = ver_res.scalar_one()
        assert version.processing_status == DocumentProcessingStatus.CHUNKED
        assert version.chunk_count > 0
        assert version.word_count > 0

        doc_res = await session.execute(select(Document).where(Document.id == doc_id))
        document = doc_res.scalar_one()
        assert document.current_version_id == ver_id
        assert document.status == DocumentProcessingStatus.CHUNKED

        chunks_res = await session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.version_id == ver_id)
            .order_by(DocumentChunk.sequence_number.asc())
        )
        chunks = chunks_res.scalars().all()
        assert len(chunks) == version.chunk_count
        assert any("Incident Severity Levels" in c.heading_hierarchy for c in chunks)


@pytest.mark.asyncio
async def test_worker_prior_version_preserved_on_new_version_failure(worker_test_env):
    session_factory, org, kb = worker_test_env

    # 1. Upload initial working version (v1)
    v1_content = b"# Version 1 Content\n\nWorking policy."
    async with session_factory() as session:
        service = DocumentService(session)
        doc, v1 = await service.upload_document(
            organization_id=org.id,
            knowledge_base_id=kb.id,
            filename="policy.md",
            content_bytes=v1_content,
        )
        doc_id = doc.id
        v1_id = v1.id

    # Process v1
    worker = DocumentWorker(session_factory=session_factory, worker_id="test-worker-1")
    await worker.run_once()

    async with session_factory() as session:
        doc_v1 = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one()
        assert doc_v1.current_version_id == v1_id
        assert doc_v1.current_version_number == 1
        assert doc_v1.status == DocumentProcessingStatus.CHUNKED

    # 2. Upload v2: valid txt file header but we simulate extraction failure by creating a version that fails
    # Let's upload a blank PDF which will trigger OCR_UNAVAILABLE
    from tests.unit.test_document_extraction import create_blank_pdf
    blank_pdf = create_blank_pdf()

    async with session_factory() as session:
        service = DocumentService(session)
        v2 = await service.upload_new_version(
            organization_id=org.id,
            document_id=doc_id,
            filename="policy_scanned.pdf",
            content_bytes=blank_pdf,
        )
        v2_id = v2.id

    # 3. Process v2
    await worker.run_once()

    # 4. Check that v2 is FAILED, but parent Document still cleanly points to v1!
    async with session_factory() as session:
        v2_res = (await session.execute(select(DocumentVersion).where(DocumentVersion.id == v2_id))).scalar_one()
        assert v2_res.processing_status == DocumentProcessingStatus.FAILED
        assert v2_res.error_code == "EXTRACTION_FAILED"

        doc_after = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one()
        # CRITICAL: Document current version is still v1!
        assert doc_after.current_version_id == v1_id
        assert doc_after.current_version_number == 1
        assert doc_after.status == DocumentProcessingStatus.CHUNKED
        assert doc_after.error_code is None


@pytest.mark.asyncio
async def test_worker_abandoned_lease_reclamation(worker_test_env):
    session_factory, org, kb = worker_test_env

    # 1. Create a document version directly with an expired lease
    now = datetime.now(UTC)
    old_time = now - timedelta(seconds=600)  # Expired lease

    async with session_factory() as session:
        doc = Document(
            id=uuid.uuid4(),
            organization_id=org.id,
            knowledge_base_id=kb.id,
            title="Stuck Doc",
            source_type="file_upload",
            original_filename="stuck.txt",
            media_type="text/plain",
            status=DocumentProcessingStatus.EXTRACTING,
            lifecycle_status="active",
            current_version_number=1,
            size_bytes=100,
            checksum="a" * 64,
        )
        session.add(doc)
        await session.flush()

        ver = DocumentVersion(
            id=uuid.uuid4(),
            organization_id=org.id,
            document_id=doc.id,
            version_number=1,
            storage_key="test_key.bin",
            original_filename="stuck.txt",
            media_type="text/plain",
            size_bytes=100,
            checksum="a" * 64,
            processing_status=DocumentProcessingStatus.EXTRACTING,
            processing_started_at=old_time,
            locked_by="crashed-worker-99",
            attempt_count=0,
        )
        session.add(ver)
        await session.commit()
        ver_id = ver.id

    worker = DocumentWorker(session_factory=session_factory, worker_id="reclaimer-worker")
    reclaimed = await worker.reclaim_abandoned_leases()
    assert reclaimed == 1

    async with session_factory() as session:
        reclaimed_ver = (await session.execute(select(DocumentVersion).where(DocumentVersion.id == ver_id))).scalar_one()
        assert reclaimed_ver.processing_status == DocumentProcessingStatus.RETRY_WAIT
        assert reclaimed_ver.attempt_count == 1
        assert reclaimed_ver.locked_by is None
