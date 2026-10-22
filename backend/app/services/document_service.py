"""Document and knowledge base management service enforcing tenant isolation and lifecycle rules."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    ConflictException,
    PayloadSizeLimitException,
    ResourceNotFoundException,
)
from app.core.logging import get_logger
from app.db.tenant import TenantScopedQuery, set_tenant_rls_context
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.enums import (
    DocumentLifecycleStatus,
    DocumentProcessingStatus,
    DocumentSourceType,
    KnowledgeBaseStatus,
)
from app.models.knowledge_base import KnowledgeBase
from app.services.extraction.validator import validate_document_file
from app.services.rag.qdrant_store import get_qdrant_store
from app.services.storage import get_storage_backend

logger = get_logger("supportgpt.document_service")


class DocumentService:
    """Service handling lifecycle operations for knowledge bases and documents."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.storage = get_storage_backend()
        self.settings = get_settings()

    async def create_knowledge_base(
        self,
        organization_id: uuid.UUID,
        name: str,
        description: str | None = None,
        config: dict | None = None,
        user_id: uuid.UUID | None = None,
    ) -> KnowledgeBase:
        """Create a new logical knowledge base collection scoped to an organization."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Knowledge base name cannot be empty.")

        # Check for unique name within organization
        existing = await self.session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.organization_id == organization_id,
                KnowledgeBase.name == clean_name,
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictException(
                f"A knowledge base with name '{clean_name}' already exists in this organization."
            )

        kb = KnowledgeBase(
            organization_id=organization_id,
            name=clean_name,
            description=description.strip() if description else None,
            status=KnowledgeBaseStatus.ACTIVE,
            config=config or {},
            created_by_user_id=user_id,
        )
        self.session.add(kb)
        try:
            await self.session.commit()
            try:
                await set_tenant_rls_context(self.session, organization_id)
            except Exception:
                pass
            await self.session.refresh(kb)
            return kb
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictException(
                "Failed to create knowledge base due to database constraint."
            ) from exc

    async def get_knowledge_base(
        self, organization_id: uuid.UUID, kb_id: uuid.UUID
    ) -> KnowledgeBase:
        """Retrieve a knowledge base ensuring organization isolation."""
        tenant = TenantScopedQuery(self.session, organization_id)
        kb = await tenant.get_knowledge_base(kb_id)
        if not kb:
            raise ResourceNotFoundException("Knowledge base", kb_id)
        return kb

    async def list_knowledge_bases(
        self, organization_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> tuple[list[KnowledgeBase], int]:
        """List knowledge bases and total count for an organization."""
        tenant = TenantScopedQuery(self.session, organization_id)
        items = list(await tenant.list_knowledge_bases(limit=limit, offset=offset))

        count_query = select(func.count(KnowledgeBase.id)).where(
            KnowledgeBase.organization_id == organization_id
        )
        total = (await self.session.execute(count_query)).scalar() or 0
        return items, total

    async def upload_document(
        self,
        organization_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        filename: str,
        content_bytes: bytes,
        title: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> tuple[Document, DocumentVersion]:
        """Upload and durably store an initial document version, queuing background processing."""
        # Validate parent knowledge base exists and belongs to tenant
        kb = await self.get_knowledge_base(organization_id, knowledge_base_id)
        if kb.status != KnowledgeBaseStatus.ACTIVE:
            raise ConflictException("Cannot upload documents to an archived knowledge base.")

        # Validate file size
        if len(content_bytes) > self.settings.MAX_DOCUMENT_UPLOAD_BYTES:
            raise PayloadSizeLimitException(
                f"File size exceeds maximum allowed upload limit of {self.settings.MAX_DOCUMENT_UPLOAD_BYTES} bytes."
            )

        # Validate file signature and media type
        verified_media_type, clean_filename = validate_document_file(content_bytes, filename)
        display_title = title.strip() if title and title.strip() else clean_filename

        document_id = uuid.uuid4()
        version_id = uuid.uuid4()
        storage_key = self.storage.generate_storage_key(
            organization_id, document_id, version_number=1
        )

        # Durably store binary object first
        storage_meta = await self.storage.store(
            storage_key=storage_key,
            data=content_bytes,
            max_bytes=self.settings.MAX_DOCUMENT_UPLOAD_BYTES,
            media_type=verified_media_type,
        )

        doc = Document(
            id=document_id,
            organization_id=organization_id,
            knowledge_base_id=knowledge_base_id,
            title=display_title,
            source_type=DocumentSourceType.FILE_UPLOAD,
            original_filename=clean_filename,
            media_type=verified_media_type,
            status=DocumentProcessingStatus.STORED,
            lifecycle_status=DocumentLifecycleStatus.ACTIVE,
            current_version_id=version_id,
            current_version_number=1,
            size_bytes=storage_meta.size_bytes,
            checksum=storage_meta.checksum,
            created_by_user_id=user_id,
        )

        version = DocumentVersion(
            id=version_id,
            organization_id=organization_id,
            document_id=document_id,
            version_number=1,
            storage_key=storage_key,
            original_filename=clean_filename,
            media_type=verified_media_type,
            size_bytes=storage_meta.size_bytes,
            checksum=storage_meta.checksum,
            processing_status=DocumentProcessingStatus.QUEUED,
            next_attempt_at=datetime.now(UTC),
            created_by_user_id=user_id,
        )

        self.session.add(doc)
        self.session.add(version)
        try:
            await self.session.commit()
            try:
                await set_tenant_rls_context(self.session, organization_id)
            except Exception:
                pass
            await self.session.refresh(doc)
            await self.session.refresh(version)
            return doc, version
        except Exception as exc:
            await self.session.rollback()
            # Clean up stored object on rollback
            await self.storage.delete(storage_key)
            logger.error("Failed to commit document upload transaction: %s", str(exc))
            raise

    async def upload_new_version(
        self,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        content_bytes: bytes,
        user_id: uuid.UUID | None = None,
    ) -> DocumentVersion:
        """Upload a new immutable version of an existing document without corrupting prior usable version."""
        tenant = TenantScopedQuery(self.session, organization_id)
        doc = await tenant.get_document(document_id)
        if not doc or doc.lifecycle_status == DocumentLifecycleStatus.DELETED:
            raise ResourceNotFoundException("Document", document_id)

        # Validate file size
        if len(content_bytes) > self.settings.MAX_DOCUMENT_UPLOAD_BYTES:
            raise PayloadSizeLimitException(
                f"File size exceeds maximum allowed upload limit of {self.settings.MAX_DOCUMENT_UPLOAD_BYTES} bytes."
            )

        verified_media_type, clean_filename = validate_document_file(content_bytes, filename)

        # Find next sequential version number
        version_count_query = select(
            func.coalesce(func.max(DocumentVersion.version_number), 0)
        ).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.organization_id == organization_id,
        )
        max_v = (await self.session.execute(version_count_query)).scalar() or 0
        next_version_num = max_v + 1

        version_id = uuid.uuid4()
        storage_key = self.storage.generate_storage_key(
            organization_id, document_id, next_version_num
        )

        storage_meta = await self.storage.store(
            storage_key=storage_key,
            data=content_bytes,
            max_bytes=self.settings.MAX_DOCUMENT_UPLOAD_BYTES,
            media_type=verified_media_type,
        )

        new_version = DocumentVersion(
            id=version_id,
            organization_id=organization_id,
            document_id=document_id,
            version_number=next_version_num,
            storage_key=storage_key,
            original_filename=clean_filename,
            media_type=verified_media_type,
            size_bytes=storage_meta.size_bytes,
            checksum=storage_meta.checksum,
            processing_status=DocumentProcessingStatus.QUEUED,
            next_attempt_at=datetime.now(UTC),
            created_by_user_id=user_id,
        )

        self.session.add(new_version)
        try:
            await self.session.commit()
            try:
                await set_tenant_rls_context(self.session, organization_id)
            except Exception:
                pass
            await self.session.refresh(new_version)
            return new_version
        except Exception as exc:
            await self.session.rollback()
            await self.storage.delete(storage_key)
            logger.error("Failed to commit new document version transaction: %s", str(exc))
            raise

    async def reprocess_document(
        self,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
    ) -> DocumentVersion:
        """Schedule reprocessing for a document version preserving previous usable content."""
        tenant = TenantScopedQuery(self.session, organization_id)
        doc = await tenant.get_document(document_id)
        if not doc or doc.lifecycle_status == DocumentLifecycleStatus.DELETED:
            raise ResourceNotFoundException("Document", document_id)

        target_version_id = version_id or doc.current_version_id
        if not target_version_id:
            raise ResourceNotFoundException("Document version for document", document_id)

        ver = await tenant.get_document_version(document_id, target_version_id)
        if not ver:
            raise ResourceNotFoundException("Document version", target_version_id)

        # Check for active worker lock
        now = datetime.now(UTC)
        if ver.processing_status in (
            DocumentProcessingStatus.EXTRACTING,
            DocumentProcessingStatus.NORMALIZING,
            DocumentProcessingStatus.CHUNKING,
        ):
            if ver.processing_started_at:
                elapsed = (now - ver.processing_started_at).total_seconds()
                if elapsed < self.settings.DOCUMENT_PROCESSING_LEASE_TIMEOUT_SECONDS:
                    raise ConflictException(
                        "Document version is currently being processed by an active worker."
                    )

        # Reset processing state for reprocessing
        ver.processing_status = DocumentProcessingStatus.QUEUED
        ver.attempt_count = 0
        ver.next_attempt_at = now
        ver.locked_by = None
        ver.processing_started_at = None
        ver.error_code = None
        ver.error_summary = None

        await self.session.commit()
        try:
            await set_tenant_rls_context(self.session, organization_id)
        except Exception:
            pass
        await self.session.refresh(ver)
        return ver

    async def soft_delete_document(
        self, organization_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document:
        """Soft delete a document removing it from active search/retrieval candidate sets."""
        tenant = TenantScopedQuery(self.session, organization_id)
        doc = await tenant.get_document(document_id)
        if not doc or doc.lifecycle_status == DocumentLifecycleStatus.DELETED:
            raise ResourceNotFoundException("Document", document_id)

        doc.lifecycle_status = DocumentLifecycleStatus.DELETED
        doc.deleted_at = datetime.now(UTC)
        await self.session.commit()
        try:
            await set_tenant_rls_context(self.session, organization_id)
        except Exception:
            pass
        await self.session.refresh(doc)

        # De-index vectors from Qdrant
        try:
            get_qdrant_store().delete_by_document_id(document_id)
        except Exception as q_exc:
            logger.warning(
                "Failed to de-index document %s from Qdrant: %s", str(document_id), str(q_exc)
            )

        return doc

    async def get_document(self, organization_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        """Retrieve a single document ensuring organization isolation."""
        tenant = TenantScopedQuery(self.session, organization_id)
        doc = await tenant.get_document(document_id)
        if not doc or doc.lifecycle_status == DocumentLifecycleStatus.DELETED:
            raise ResourceNotFoundException("Document", document_id)
        return doc

    async def list_documents(
        self,
        organization_id: uuid.UUID,
        kb_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        """List active documents and total count for an organization / knowledge base."""
        tenant = TenantScopedQuery(self.session, organization_id)
        items = list(await tenant.list_documents(kb_id=kb_id, limit=limit, offset=offset))

        count_query = select(func.count(Document.id)).where(
            Document.organization_id == organization_id,
            Document.lifecycle_status != DocumentLifecycleStatus.DELETED,
        )
        if kb_id:
            count_query = count_query.where(Document.knowledge_base_id == kb_id)

        total = (await self.session.execute(count_query)).scalar() or 0
        return items, total

    async def list_document_versions(
        self, organization_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[DocumentVersion]:
        """List all version revisions of a document."""
        tenant = TenantScopedQuery(self.session, organization_id)
        doc = await tenant.get_document(document_id)
        if not doc or doc.lifecycle_status == DocumentLifecycleStatus.DELETED:
            raise ResourceNotFoundException("Document", document_id)

        return list(await tenant.list_document_versions(document_id))

    async def get_document_chunks(
        self,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DocumentChunk], int]:
        """List persisted chunks with provenance for a specific document version."""
        tenant = TenantScopedQuery(self.session, organization_id)
        doc = await tenant.get_document(document_id)
        if not doc or doc.lifecycle_status == DocumentLifecycleStatus.DELETED:
            raise ResourceNotFoundException("Document", document_id)

        target_version_id = version_id or doc.current_version_id
        if not target_version_id:
            return [], 0

        chunks = list(
            await tenant.list_document_chunks(target_version_id, limit=limit, offset=offset)
        )

        count_query = select(func.count(DocumentChunk.id)).where(
            DocumentChunk.version_id == target_version_id,
            DocumentChunk.organization_id == organization_id,
        )
        total = (await self.session.execute(count_query)).scalar() or 0
        return chunks, total
