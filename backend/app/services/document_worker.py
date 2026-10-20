"""Durable background document worker with lease recovery, transactional chunking, and tenant safety."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import DocumentExtractionException
from app.core.logging import get_logger
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentProcessingStatus
from app.services.chunking import HierarchicalStructuralChunker, TextNormalizer
from app.services.extraction import get_extractor
from app.services.rag.embedding import BaseEmbeddingProvider, get_embedding_provider
from app.services.rag.qdrant_store import QdrantStoreManager, get_qdrant_store
from app.services.storage import get_storage_backend

logger = get_logger("supportgpt.document_worker")


async def _set_worker_admin_context(session: AsyncSession) -> None:
    """Set system admin context if supported by the database dialect."""
    try:
        bind = session.bind
        dialect = bind.dialect.name if bind else ""
        if dialect == "postgresql":
            await session.execute(text("SELECT set_config('app.is_system_admin', 'true', true)"))
    except Exception:
        pass


class DocumentWorker:
    """Asynchronous background worker processing uploaded documents through the extraction, chunking, and vector indexing pipeline."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings | None = None,
        worker_id: str | None = None,
        embedding_provider: BaseEmbeddingProvider | None = None,
        qdrant_store: QdrantStoreManager | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.worker_id = worker_id or f"doc-worker-{uuid.uuid4().hex[:8]}"
        self.storage = get_storage_backend()
        self.normalizer = TextNormalizer()
        self.chunker = HierarchicalStructuralChunker(
            chunk_size=self.settings.DEFAULT_CHUNK_SIZE_CHARS,
            chunk_overlap=self.settings.DEFAULT_CHUNK_OVERLAP_CHARS,
        )
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.qdrant_store = qdrant_store or get_qdrant_store()

    async def reclaim_abandoned_leases(self) -> int:
        """Identify versions with expired worker leases and reschedule or fail them."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=self.settings.DOCUMENT_PROCESSING_LEASE_TIMEOUT_SECONDS)

        async with self.session_factory() as session:
            await _set_worker_admin_context(session)

            query = select(DocumentVersion).where(
                DocumentVersion.processing_status.in_(
                    [
                        DocumentProcessingStatus.EXTRACTING,
                        DocumentProcessingStatus.NORMALIZING,
                        DocumentProcessingStatus.CHUNKING,
                    ]
                ),
                DocumentVersion.processing_started_at < cutoff,
            )
            result = await session.execute(query)
            abandoned = result.scalars().all()

            reclaimed_count = 0
            for ver in abandoned:
                ver.attempt_count += 1
                if ver.attempt_count >= self.settings.DOCUMENT_PROCESSING_MAX_ATTEMPTS:
                    ver.processing_status = DocumentProcessingStatus.FAILED
                    ver.error_code = "LEASE_TIMEOUT_EXCEEDED"
                    ver.error_summary = (
                        f"Processing lease abandoned and exceeded maximum attempts ({self.settings.DOCUMENT_PROCESSING_MAX_ATTEMPTS})."
                    )
                    ver.locked_by = None
                    ver.processing_started_at = None
                else:
                    ver.processing_status = DocumentProcessingStatus.RETRY_WAIT
                    backoff_delay = 2 ** ver.attempt_count * 5
                    ver.next_attempt_at = now + timedelta(seconds=backoff_delay)
                    ver.locked_by = None
                    ver.processing_started_at = None

                reclaimed_count += 1

            if reclaimed_count > 0:
                await session.commit()
                logger.warning(
                    "Reclaimed %d abandoned document processing leases.",
                    reclaimed_count,
                    extra={"worker_id": self.worker_id},
                )
            return reclaimed_count

    async def claim_batch(self, batch_size: int | None = None) -> list[uuid.UUID]:
        """Claim a batch of queued document versions using FOR UPDATE SKIP LOCKED."""
        limit = batch_size or self.settings.DOCUMENT_PROCESSING_BATCH_SIZE
        now = datetime.now(UTC)

        async with self.session_factory() as session:
            await _set_worker_admin_context(session)

            # Select and lock eligible jobs
            query = (
                select(DocumentVersion)
                .where(
                    DocumentVersion.processing_status.in_(
                        [
                            DocumentProcessingStatus.QUEUED,
                            DocumentProcessingStatus.RETRY_WAIT,
                        ]
                    ),
                    (DocumentVersion.next_attempt_at.is_(None))
                    | (DocumentVersion.next_attempt_at <= now),
                )
                .order_by(DocumentVersion.next_attempt_at.asc(), DocumentVersion.created_at.asc())
                .limit(limit)
            )

            bind = session.bind
            dialect_name = bind.dialect.name if bind else ""
            if dialect_name == "postgresql":
                query = query.with_for_update(skip_locked=True)

            result = await session.execute(query)
            versions = result.scalars().all()
            claimed_ids: list[uuid.UUID] = []

            for ver in versions:
                ver.processing_status = DocumentProcessingStatus.EXTRACTING
                ver.locked_by = self.worker_id
                ver.processing_started_at = now
                claimed_ids.append(ver.id)

            if claimed_ids:
                await session.commit()
            return claimed_ids

    async def process_version(self, version_id: uuid.UUID) -> bool:
        """Process a single document version through extraction, normalization, and chunking."""
        async with self.session_factory() as session:
            await _set_worker_admin_context(session)

            ver_query = select(DocumentVersion).where(DocumentVersion.id == version_id)
            version = (await session.execute(ver_query)).scalar_one_or_none()
            if not version:
                logger.error("Document version %s not found for processing.", str(version_id))
                return False

            doc_query = select(Document).where(Document.id == version.document_id)
            document = (await session.execute(doc_query)).scalar_one_or_none()
            if not document:
                logger.error("Parent document %s not found for version %s.", str(version.document_id), str(version_id))
                version.processing_status = DocumentProcessingStatus.FAILED
                version.error_code = "PARENT_DOCUMENT_NOT_FOUND"
                version.error_summary = "Parent document record could not be located."
                await session.commit()
                return False

            now = datetime.now(UTC)
            try:
                # 1. Read binary content from storage
                content_bytes = await self.storage.read_bytes(version.storage_key)

                # 2. Extract text using format extractor
                version.processing_status = DocumentProcessingStatus.EXTRACTING
                extractor = get_extractor(version.media_type)
                extract_res = extractor.extract(content_bytes, version.original_filename)

                # 3. Deterministic normalization
                version.processing_status = DocumentProcessingStatus.NORMALIZING
                normalized_text = self.normalizer.normalize(extract_res.text)

                # 4. Reproducible structural chunking
                version.processing_status = DocumentProcessingStatus.CHUNKING
                chunk_items = self.chunker.chunk(normalized_text)

                # 5. Atomic persistence of chunks
                # Remove any existing chunks for this version (idempotency / reprocessing guarantee)
                await session.execute(
                    delete(DocumentChunk).where(DocumentChunk.version_id == version.id)
                )

                chunk_models: list[DocumentChunk] = []
                for c in chunk_items:
                    chunk_models.append(
                        DocumentChunk(
                            id=uuid.uuid4(),
                            organization_id=version.organization_id,
                            knowledge_base_id=document.knowledge_base_id,
                            document_id=document.id,
                            version_id=version.id,
                            sequence_number=c.sequence_number,
                            content=c.content,
                            word_count=c.word_count,
                            character_count=c.character_count,
                            start_char_idx=c.start_char_idx,
                            end_char_idx=c.end_char_idx,
                            heading_hierarchy=c.heading_hierarchy,
                            checksum=c.checksum,
                            pipeline_version=c.pipeline_version,
                        )
                    )

                session.add_all(chunk_models)
                await session.flush()

                # 6. Real Vector Indexing into Qdrant
                chunk_texts = [c.content for c in chunk_models]
                if chunk_texts:
                    version.processing_status = DocumentProcessingStatus.READY_FOR_INDEXING
                    # Delete any previous vector points for this version (reprocessing idempotency)
                    self.qdrant_store.delete_by_version_id(version.id)
                    # Generate real dense vector embeddings using configured provider
                    vectors = await self.embedding_provider.embed_texts(chunk_texts)
                    chunks_with_vectors = list(zip(chunk_models, vectors, strict=True))
                    self.qdrant_store.upsert_chunks(chunks_with_vectors)

                # 7. Update version status and metadata
                version.extractor_name = extractor.name
                version.extractor_version = extractor.version
                version.chunker_name = "HierarchicalStructuralChunker"
                version.chunker_version = self.chunker.version
                version.chunk_count = len(chunk_items)
                version.word_count = extract_res.word_count
                version.character_count = len(normalized_text)
                version.processing_status = DocumentProcessingStatus.INDEXED
                version.error_code = None
                version.error_summary = None
                version.locked_by = None
                version.processing_started_at = None

                # 8. Atomically promote version in parent Document if this is latest or current
                if document.current_version_number <= version.version_number:
                    document.current_version_id = version.id
                    document.current_version_number = version.version_number
                    document.status = DocumentProcessingStatus.INDEXED
                    document.error_code = None
                    document.error_summary = None

                await session.commit()
                logger.info(
                    "Successfully processed and indexed document %s version %d (%d chunks).",
                    str(document.id),
                    version.version_number,
                    len(chunk_items),
                    extra={"document_id": str(document.id), "version_id": str(version.id)},
                )
                return True

            except DocumentExtractionException as exc:
                # Permanent extraction failure (e.g. OCR unavailable / malformed internal structure)
                logger.warning(
                    "Extraction failed permanently for document version %s: %s",
                    str(version_id),
                    str(exc),
                )
                version.processing_status = DocumentProcessingStatus.FAILED
                version.error_code = "EXTRACTION_FAILED"
                version.error_summary = str(exc)[:500]
                version.locked_by = None
                version.processing_started_at = None

                # If this was initial version v1 and has no published version, update document status
                if document.current_version_id == version.id:
                    document.status = DocumentProcessingStatus.FAILED
                    document.error_code = "EXTRACTION_FAILED"
                    document.error_summary = str(exc)[:500]

                await session.commit()
                return False

            except Exception as exc:
                # Transient failure: retry with exponential backoff
                logger.exception(
                    "Unexpected error processing document version %s: %s",
                    str(version_id),
                    str(exc),
                )
                version.attempt_count += 1
                if version.attempt_count >= self.settings.DOCUMENT_PROCESSING_MAX_ATTEMPTS:
                    version.processing_status = DocumentProcessingStatus.FAILED
                    version.error_code = "MAX_ATTEMPTS_EXCEEDED"
                    version.error_summary = f"Exceeded maximum attempts ({self.settings.DOCUMENT_PROCESSING_MAX_ATTEMPTS}): {str(exc)[:400]}"
                else:
                    version.processing_status = DocumentProcessingStatus.RETRY_WAIT
                    backoff = 2 ** version.attempt_count * 5
                    version.next_attempt_at = now + timedelta(seconds=backoff)

                version.locked_by = None
                version.processing_started_at = None
                await session.commit()
                return False

    async def run_once(self) -> int:
        """Execute one complete processing cycle: reclaim abandoned leases then process claimed batch."""
        await self.reclaim_abandoned_leases()
        claimed = await self.claim_batch()
        processed_count = 0
        for vid in claimed:
            success = await self.process_version(vid)
            if success:
                processed_count += 1
        return processed_count

    async def run_worker_loop(self, stop_event: asyncio.Event, poll_interval: float = 2.0) -> None:
        """Run the document processing worker daemon until cancelled."""
        logger.info("Starting document processing worker %s", self.worker_id)
        while not stop_event.is_set():
            try:
                processed = await self.run_once()
                if processed == 0:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in document worker loop: %s", str(exc))
                await asyncio.sleep(poll_interval)

        logger.info("Document processing worker %s stopped.", self.worker_id)
