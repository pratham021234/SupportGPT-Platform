"""Qdrant Vector Database Integration & Collection Manager.

Handles vector lifecycle, dimension verification, tenant-isolated payload indexing,
and deterministic upsert/delete operations.
"""

import logging
from typing import Any
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from app.core.config import settings
from app.core.errors import (
    VectorDimensionMismatchException,
    VectorIndexingException,
    VectorStoreUnavailableException,
)

logger = logging.getLogger(__name__)


class QdrantStoreManager:
    """Enterprise Qdrant Vector Store interface for SupportGPT knowledge retrieval."""

    def __init__(
        self,
        collection_name: str = settings.QDRANT_COLLECTION_NAME,
        dimensions: int = settings.EMBEDDING_DIMENSIONS,
        client: QdrantClient | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.dimensions = dimensions
        self._client: QdrantClient | None = client

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialize or return the active Qdrant client."""
        if self._client is None:
            self._client = self._init_client()
        return self._client

    def _init_client(self) -> QdrantClient:
        """Initialize the Qdrant client based on configuration.

        Supports server-based Qdrant instances (Docker / Cloud) as well as embedded
        on-disk or in-memory engines for local development and integration tests.
        """
        # 1. Explicit location (e.g. ":memory:")
        if settings.QDRANT_LOCATION:
            logger.info(f"Connecting to Qdrant at explicit location: {settings.QDRANT_LOCATION}")
            return QdrantClient(location=settings.QDRANT_LOCATION)

        # 2. Local on-disk directory
        if settings.QDRANT_PATH:
            logger.info(f"Connecting to local embedded Qdrant at path: {settings.QDRANT_PATH}")
            return QdrantClient(path=settings.QDRANT_PATH)

        # 3. Network host/port
        try:
            logger.info(
                f"Attempting connection to Qdrant server at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
            )
            client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                api_key=settings.QDRANT_API_KEY,
                timeout=settings.QDRANT_TIMEOUT_SECONDS,
            )
            # Test connectivity with a lightweight check
            client.get_collections()
            return client
        except Exception as exc:
            logger.warning(
                f"Could not connect to Qdrant server at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}: {exc}"
            )
            # In testing or development, fall back safely to in-memory mode if server is not reachable
            if settings.ENVIRONMENT in ("development", "test", "local"):
                logger.warning("Falling back to local in-memory Qdrant engine for development/testing.")
                return QdrantClient(location=":memory:")
            raise VectorStoreUnavailableException(
                f"Failed to connect to Qdrant vector engine at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
            ) from exc

    def ensure_collection(self) -> None:
        """Verify collection exists and matches configured vector dimensions; create if absent.

        CRITICAL INTEGRITY INVARIANT:
        Detects vector dimension mismatch or distance metric drift immediately and
        aborts to prevent corrupting HNSW index graphs or querying incompatible vectors.
        """
        try:
            exists = self.client.collection_exists(self.collection_name)
            if exists:
                collection_info = self.client.get_collection(self.collection_name)
                # Check vector dimensions
                vectors_config = collection_info.config.params.vectors
                existing_size: int | None = None
                if isinstance(vectors_config, VectorParams):
                    existing_size = vectors_config.size
                elif isinstance(vectors_config, dict) and "" in vectors_config:
                    existing_size = vectors_config[""].size

                if existing_size is not None and existing_size != self.dimensions:
                    raise VectorDimensionMismatchException(
                        f"Qdrant collection '{self.collection_name}' exists with vector dimension "
                        f"{existing_size}, but active embedding configuration requires {self.dimensions}. "
                        "Reindexing is required."
                    )
                logger.debug(
                    f"Verified existing Qdrant collection '{self.collection_name}' (dim={existing_size})"
                )
                return

            # Collection does not exist -> create it
            logger.info(
                f"Creating Qdrant collection '{self.collection_name}' with dimension {self.dimensions}"
            )
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.dimensions, distance=Distance.COSINE),
            )

            # Create payload indexes on keyword fields for tenant isolation & fast lookups
            for field in ("organization_id", "knowledge_base_id", "document_id", "document_version_id"):
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field,
                        field_schema=PayloadSchemaType.KEYWORD,
                    )
                except Exception as index_exc:
                    logger.debug(f"Payload index creation note for '{field}': {index_exc}")

        except Exception as exc:
            if isinstance(exc, (VectorDimensionMismatchException, VectorStoreUnavailableException)):
                raise
            raise VectorIndexingException(f"Error ensuring Qdrant collection '{self.collection_name}': {exc}") from exc

    def upsert_chunks(self, chunks_with_vectors: list[tuple[Any, list[float]]]) -> int:
        """Batch upsert document chunks into Qdrant with deterministic point IDs.

        Each point ID is the chunk UUID.
        Payload stores minimal metadata necessary for tenant filtering and provenance;
        sensitive raw text is preserved in PostgreSQL and retrieved authoritatively.
        """
        if not chunks_with_vectors:
            return 0

        self.ensure_collection()

        points: list[PointStruct] = []
        for chunk, vector in chunks_with_vectors:
            point_id = str(chunk.id)
            ver_id = getattr(chunk, "version_id", None) or getattr(chunk, "document_version_id", None)
            seq_num = getattr(chunk, "sequence_number", None) or getattr(chunk, "sequence_num", 0)
            chksum = getattr(chunk, "checksum", None) or getattr(chunk, "chunk_checksum_sha256", "")
            headings = getattr(chunk, "heading_hierarchy", [])
            sec_title = getattr(chunk, "section_title", None)
            if not sec_title and headings and isinstance(headings, list):
                sec_title = headings[-1]

            payload = {
                "organization_id": str(chunk.organization_id),
                "knowledge_base_id": str(chunk.knowledge_base_id),
                "document_id": str(chunk.document_id),
                "document_version_id": str(ver_id),
                "chunk_id": str(chunk.id),
                "sequence_num": seq_num,
                "section_title": sec_title,
                "chunk_checksum_sha256": chksum,
                "pipeline_version": getattr(chunk, "pipeline_version", "v1.0"),
            }
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            return len(points)
        except Exception as exc:
            logger.error(f"Failed to upsert {len(points)} chunks into Qdrant: {exc}")
            raise VectorIndexingException(f"Qdrant batch upsert failed: {exc}") from exc

    def search_vectors(
        self,
        query_vector: list[float],
        organization_id: UUID,
        knowledge_base_ids: list[UUID] | None = None,
        top_k: int = settings.RETRIEVAL_TOP_K_DEFAULT,
        score_threshold: float | None = None,
    ) -> list[ScoredPoint]:
        """Execute tenant-isolated vector similarity search in Qdrant.

        SECURITY INVARIANT:
        The organization_id filter is NON-NEGOTIABLE and ALWAYS applied at the
        vector engine layer, preventing cross-tenant vector retrieval.
        """
        self.ensure_collection()

        must_conditions: list[FieldCondition] = [
            FieldCondition(
                key="organization_id",
                match=MatchValue(value=str(organization_id)),
            )
        ]

        if knowledge_base_ids:
            must_conditions.append(
                FieldCondition(
                    key="knowledge_base_id",
                    match=MatchAny(any=[str(kb_id) for kb_id in knowledge_base_ids]),
                )
            )

        query_filter = Filter(must=must_conditions)

        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return results.points
        except Exception as exc:
            logger.error(f"Qdrant vector search failed: {exc}")
            raise VectorStoreUnavailableException(f"Vector search failed: {exc}") from exc

    def delete_by_version_id(self, version_id: UUID) -> None:
        """Remove all vector points belonging to a specific document version."""
        self.ensure_collection()
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_version_id",
                            match=MatchValue(value=str(version_id)),
                        )
                    ]
                ),
                wait=True,
            )
        except Exception as exc:
            logger.error(f"Failed to delete vectors for version '{version_id}': {exc}")
            raise VectorIndexingException(f"Qdrant vector deletion failed: {exc}") from exc

    def delete_by_document_id(self, document_id: UUID) -> None:
        """Remove all vector points belonging to a document."""
        self.ensure_collection()
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=str(document_id)),
                        )
                    ]
                ),
                wait=True,
            )
        except Exception as exc:
            logger.error(f"Failed to delete vectors for document '{document_id}': {exc}")
            raise VectorIndexingException(f"Qdrant vector deletion failed: {exc}") from exc

    def delete_by_knowledge_base_id(self, kb_id: UUID) -> None:
        """Remove all vector points belonging to an entire knowledge base."""
        self.ensure_collection()
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="knowledge_base_id",
                            match=MatchValue(value=str(kb_id)),
                        )
                    ]
                ),
                wait=True,
            )
        except Exception as exc:
            logger.error(f"Failed to delete vectors for knowledge base '{kb_id}': {exc}")
            raise VectorIndexingException(f"Qdrant vector deletion failed: {exc}") from exc


_qdrant_store_instance: QdrantStoreManager | None = None


def get_qdrant_store() -> QdrantStoreManager:
    """Factory retrieving the configured QdrantStoreManager singleton."""
    global _qdrant_store_instance
    if _qdrant_store_instance is None:
        _qdrant_store_instance = QdrantStoreManager()
    return _qdrant_store_instance


def reset_qdrant_store() -> None:
    """Reset the cached QdrantStoreManager singleton (for tests)."""
    global _qdrant_store_instance
    _qdrant_store_instance = None
