"""Disaster recovery utility: Reconstruct Qdrant vector indexes from PostgreSQL.

PostgreSQL is the authoritative single source of truth for all knowledge
bases, documents, versions, and chunks. If the vector store is lost, wiped,
or corrupted, this script reconstructs collections and reindexes all chunks.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_factory
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentProcessingStatus
from app.services.rag.embedding import get_embedding_provider
from app.services.rag.qdrant_store import QdrantStoreManager

logger = get_logger("supportgpt.reindex")


async def reconstruct_vector_indexes(batch_size: int = 50) -> dict:
    """Read all indexed chunks from PostgreSQL and re-upsert into Qdrant."""
    logger.info("Initiating vector disaster recovery re-indexing from PostgreSQL...")

    # 1. Initialize embedding provider and Qdrant store
    provider = get_embedding_provider()
    store = QdrantStoreManager(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        dimensions=provider.dimensions,
    )
    store.ensure_collection()
    logger.info(
        "Qdrant collection '%s' verified (Dimensions: %d, Distance: Cosine)",
        settings.QDRANT_COLLECTION_NAME,
        provider.dimensions,
    )

    reindexed_count = 0
    total_chunks = 0

    async with async_session_factory() as session:
        # Query chunks belonging to actively indexed document versions
        query = (
            select(DocumentChunk)
            .join(DocumentVersion, DocumentChunk.version_id == DocumentVersion.id)
            .where(DocumentVersion.processing_status == DocumentProcessingStatus.INDEXED)
            .order_by(DocumentChunk.created_at.asc())
        )

        result = await session.execute(query)
        chunks: Sequence[DocumentChunk] = result.scalars().all()
        total_chunks = len(chunks)
        logger.info("Found %d authoritative active document chunks in PostgreSQL", total_chunks)

        if total_chunks == 0:
            logger.info("No active document chunks require indexing.")
            return {"status": "completed", "total_chunks": 0, "reindexed_count": 0}

        # Process in batches
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.content for c in batch]
            logger.info("Embedding batch %d-%d of %d...", i + 1, min(i + batch_size, total_chunks), total_chunks)

            # Generate dense embeddings
            vectors = await provider.embed_texts(texts)

            # Upsert into Qdrant using (chunk, vector) tuples
            chunks_with_vectors = list(zip(batch, vectors, strict=True))
            store.upsert_chunks(chunks_with_vectors)
            reindexed_count += len(chunks_with_vectors)

    logger.info("Vector re-indexing completed successfully: %d / %d chunks indexed.", reindexed_count, total_chunks)
    return {
        "status": "completed",
        "total_chunks": total_chunks,
        "reindexed_count": reindexed_count,
        "collection": settings.QDRANT_COLLECTION_NAME,
        "dimensions": provider.dimensions,
    }


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Reconstruct Qdrant Vectors from PostgreSQL")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for embedding")
    args = parser.parse_args()

    try:
        asyncio.run(reconstruct_vector_indexes(batch_size=args.batch_size))
    except Exception as exc:
        logger.exception("Vector re-indexing failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
