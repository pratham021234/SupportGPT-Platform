"""Unit tests for Qdrant vector store manager, collection verification, and tenant filtering."""

import uuid

import pytest
from qdrant_client import QdrantClient

from app.core.errors import (
    VectorDimensionMismatchException,
)
from app.services.rag.qdrant_store import QdrantStoreManager


class FakeChunk:
    """Mock chunk for unit testing vector store upsert."""

    def __init__(
        self,
        chunk_id: uuid.UUID,
        org_id: uuid.UUID,
        kb_id: uuid.UUID,
        doc_id: uuid.UUID,
        ver_id: uuid.UUID,
        seq: int = 1,
        section_title: str | None = "Architecture",
    ) -> None:
        self.id = chunk_id
        self.organization_id = org_id
        self.knowledge_base_id = kb_id
        self.document_id = doc_id
        self.document_version_id = ver_id
        self.sequence_num = seq
        self.section_title = section_title
        self.chunk_checksum_sha256 = "abc123hash"
        self.pipeline_version = "v1.0"


def test_qdrant_collection_creation_and_dimension_verification():
    """Verify Qdrant collection is created and dimension mismatches are prevented."""
    raw_client = QdrantClient(location=":memory:")
    manager = QdrantStoreManager(
        collection_name="test_col_dims",
        dimensions=384,
        client=raw_client,
    )

    # 1. Ensure collection creates with 384 dimensions
    manager.ensure_collection()
    assert raw_client.collection_exists("test_col_dims") is True

    # 2. Re-ensuring with same dimensions succeeds
    manager.ensure_collection()

    # 3. New manager with mismatched dimension raises VectorDimensionMismatchException
    mismatched_manager = QdrantStoreManager(
        collection_name="test_col_dims",
        dimensions=1536,  # OpenAI dimensions vs 384 existing
        client=raw_client,
    )
    with pytest.raises(VectorDimensionMismatchException) as exc_info:
        mismatched_manager.ensure_collection()
    assert "vector dimension 384" in str(exc_info.value.message)
    assert "requires 1536" in str(exc_info.value.message)


def test_qdrant_tenant_filtered_search_and_batch_upsert():
    """Verify vector search enforces strict organization isolation in Qdrant."""
    raw_client = QdrantClient(location=":memory:")
    manager = QdrantStoreManager(
        collection_name="test_tenant_search",
        dimensions=4,
        client=raw_client,
    )

    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    kb_a = uuid.uuid4()
    kb_b = uuid.uuid4()
    doc_a = uuid.uuid4()
    doc_b = uuid.uuid4()
    ver_a = uuid.uuid4()
    ver_b = uuid.uuid4()

    chunk_a = FakeChunk(uuid.uuid4(), org_a, kb_a, doc_a, ver_a)
    chunk_b = FakeChunk(uuid.uuid4(), org_b, kb_b, doc_b, ver_b)

    # Upsert chunk A (Org A) and chunk B (Org B)
    vec_a = [0.9, 0.1, 0.0, 0.0]
    vec_b = [0.95, 0.05, 0.0, 0.0]

    count = manager.upsert_chunks([(chunk_a, vec_a), (chunk_b, vec_b)])
    assert count == 2

    # Query matching vec_b closely, but authorized as Org A
    query_vec = [0.95, 0.05, 0.0, 0.0]
    results_org_a = manager.search_vectors(
        query_vector=query_vec,
        organization_id=org_a,
        top_k=5,
    )

    # Org A search MUST NOT see Org B's vector point
    assert len(results_org_a) == 1
    assert results_org_a[0].id == str(chunk_a.id)
    assert results_org_a[0].payload["organization_id"] == str(org_a)

    # Query as Org B sees only chunk B
    results_org_b = manager.search_vectors(
        query_vector=query_vec,
        organization_id=org_b,
        top_k=5,
    )
    assert len(results_org_b) == 1
    assert results_org_b[0].id == str(chunk_b.id)
    assert results_org_b[0].payload["organization_id"] == str(org_b)


def test_qdrant_deletion_by_version_and_document():
    """Verify points can be purged by document version or document ID."""
    raw_client = QdrantClient(location=":memory:")
    manager = QdrantStoreManager(
        collection_name="test_deletion",
        dimensions=4,
        client=raw_client,
    )

    org_id = uuid.uuid4()
    kb_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_1 = uuid.uuid4()
    ver_2 = uuid.uuid4()

    c1 = FakeChunk(uuid.uuid4(), org_id, kb_id, doc_id, ver_1, seq=1)
    c2 = FakeChunk(uuid.uuid4(), org_id, kb_id, doc_id, ver_1, seq=2)
    c3 = FakeChunk(uuid.uuid4(), org_id, kb_id, doc_id, ver_2, seq=1)

    manager.upsert_chunks(
        [
            (c1, [0.1, 0.2, 0.3, 0.4]),
            (c2, [0.2, 0.3, 0.4, 0.5]),
            (c3, [0.3, 0.4, 0.5, 0.6]),
        ]
    )

    # Delete ver_1 points
    manager.delete_by_version_id(ver_1)

    # Search should now only return c3 (ver_2)
    results = manager.search_vectors(
        query_vector=[0.1, 0.2, 0.3, 0.4],
        organization_id=org_id,
        top_k=10,
    )
    assert len(results) == 1
    assert results[0].id == str(c3.id)

    # Delete entire document
    manager.delete_by_document_id(doc_id)
    results_after_doc_del = manager.search_vectors(
        query_vector=[0.1, 0.2, 0.3, 0.4],
        organization_id=org_id,
        top_k=10,
    )
    assert len(results_after_doc_del) == 0
