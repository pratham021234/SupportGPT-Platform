"""Retrieval-Augmented Generation (RAG) Subsystem for SupportGPT AI.

Integrates real semantic embedding generation, tenant-isolated Qdrant vector indexing,
hybrid retrieval, authoritative PostgreSQL lifecycle verification, and evidence-grounded
answer generation with prompt-injection defense and verified citations.
"""

from app.services.rag.answer import GroundedAnswerService
from app.services.rag.embedding import (
    BaseEmbeddingProvider,
    DeterministicMockEmbeddingProvider,
    EmbeddingMetadata,
    FastEmbedEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
    reset_embedding_provider,
)
from app.services.rag.evidence import CitationItem, EvidenceItem, GroundedAnswerResult
from app.services.rag.qdrant_store import (
    QdrantStoreManager,
    get_qdrant_store,
    reset_qdrant_store,
)
from app.services.rag.retrieval import RetrievalService

__all__ = [
    "BaseEmbeddingProvider",
    "CitationItem",
    "DeterministicMockEmbeddingProvider",
    "EmbeddingMetadata",
    "EvidenceItem",
    "FastEmbedEmbeddingProvider",
    "GroundedAnswerResult",
    "GroundedAnswerService",
    "OpenAIEmbeddingProvider",
    "QdrantStoreManager",
    "RetrievalService",
    "get_embedding_provider",
    "get_qdrant_store",
    "reset_embedding_provider",
    "reset_qdrant_store",
]
