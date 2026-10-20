"""Authoritative Knowledge Retrieval Service.

Implements query normalization, real vector similarity search, optional hybrid
lexical search via Reciprocal Rank Fusion (RRF), and strict authoritative
PostgreSQL record verification against document lifecycle and active version status.
"""

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import InvalidRetrievalQueryException
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.enums import DocumentLifecycleStatus, DocumentProcessingStatus, KnowledgeBaseStatus
from app.models.knowledge_base import KnowledgeBase
from app.services.rag.embedding import BaseEmbeddingProvider, get_embedding_provider
from app.services.rag.evidence import EvidenceItem
from app.services.rag.qdrant_store import QdrantStoreManager, get_qdrant_store

logger = logging.getLogger(__name__)


class RetrievalService:
    """Dedicated knowledge retrieval service enforcing tenant isolation and authoritative verification."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: BaseEmbeddingProvider | None = None,
        qdrant_store: QdrantStoreManager | None = None,
    ) -> None:
        self.session = session
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.qdrant_store = qdrant_store or get_qdrant_store()

    def validate_and_normalize_query(self, query: str) -> str:
        """Validate search query bounds and normalize input text."""
        if not query or not query.strip():
            raise InvalidRetrievalQueryException("Search query cannot be empty or whitespace only.")

        normalized = query.strip()
        if len(normalized) < 2:
            raise InvalidRetrievalQueryException(
                "Search query must be at least 2 characters in length."
            )
        if len(normalized) > 2000:
            raise InvalidRetrievalQueryException(
                "Search query exceeds maximum allowed length of 2000 characters."
            )

        return normalized

    async def retrieve(
        self,
        query: str,
        organization_id: UUID,
        knowledge_base_ids: list[UUID] | None = None,
        top_k: int = settings.RETRIEVAL_TOP_K_DEFAULT,
        min_score: float | None = settings.RETRIEVAL_SIMILARITY_THRESHOLD,
        enable_hybrid: bool = settings.RETRIEVAL_ENABLE_HYBRID,
    ) -> tuple[list[EvidenceItem], float]:
        """Execute authorized retrieval and return verified evidence items with latency tracking.

        SECURITY INVARIANTS:
        1. Query embedding generated using authorized provider.
        2. Qdrant filter strictly restricts search to organization_id.
        3. Returned chunk IDs are verified against authoritative PostgreSQL records.
        4. Stale, deleted, archived, or inactive document versions are discarded.
        """
        start_time = time.perf_counter()
        normalized_query = self.validate_and_normalize_query(query)
        bounded_top_k = max(1, min(top_k, settings.RETRIEVAL_TOP_K_MAX))

        # 1. Vector Search via Qdrant
        query_vector = await self.embedding_provider.embed_query(normalized_query)
        # Fetch candidate pool (2x top_k) to allow for post-retrieval lifecycle filtering
        fetch_limit = min(bounded_top_k * 3, 60)
        vector_points = self.qdrant_store.search_vectors(
            query_vector=query_vector,
            organization_id=organization_id,
            knowledge_base_ids=knowledge_base_ids,
            top_k=fetch_limit,
            score_threshold=min_score,
        )

        vector_ranked_ids: list[UUID] = []
        vector_scores: dict[UUID, float] = {}
        for pt in vector_points:
            try:
                cid = UUID(str(pt.id))
                vector_ranked_ids.append(cid)
                vector_scores[cid] = float(pt.score)
            except Exception:
                continue

        # 2. Optional Lexical / Full-Text Search in PostgreSQL
        lexical_ranked_ids: list[UUID] = []
        if enable_hybrid:
            lexical_ranked_ids = await self._search_lexical(
                query=normalized_query,
                organization_id=organization_id,
                knowledge_base_ids=knowledge_base_ids,
                limit=fetch_limit,
            )

        # 3. Combine rankings via Reciprocal Rank Fusion (RRF)
        candidate_ids = self._fuse_rankings(
            vector_ranks=vector_ranked_ids,
            lexical_ranks=lexical_ranked_ids,
            vector_scores=vector_scores,
            rrf_k=settings.RETRIEVAL_RRF_K,
        )

        if not candidate_ids:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return [], latency_ms

        # 4. Authoritative Database Verification
        evidence_items = await self._verify_and_assemble_evidence(
            candidate_items=candidate_ids,
            organization_id=organization_id,
            top_k=bounded_top_k,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return evidence_items, latency_ms

    async def _search_lexical(
        self,
        query: str,
        organization_id: UUID,
        knowledge_base_ids: list[UUID] | None,
        limit: int,
    ) -> list[UUID]:
        """Perform lexical full-text search against PostgreSQL document_chunks."""
        try:
            bind = self.session.bind
            dialect_name = bind.dialect.name if bind else ""

            if dialect_name == "postgresql":
                # PostgreSQL native tsvector full-text search
                sql = """
                    SELECT c.id
                    FROM document_chunks c
                    WHERE c.organization_id = :org_id
                      AND to_tsvector('english', c.content) @@ plainto_tsquery('english', :query)
                """
                params: dict[str, Any] = {
                    "org_id": organization_id,
                    "query": query,
                    "limit": limit,
                }
                if knowledge_base_ids:
                    sql += " AND c.knowledge_base_id = ANY(:kb_ids)"
                    params["kb_ids"] = knowledge_base_ids

                sql += " LIMIT :limit"
                result = await self.session.execute(text(sql), params)
                return [row[0] for row in result.fetchall()]
            else:
                # SQLite / non-Postgres test fallback using substring LIKE
                stmt = select(DocumentChunk.id).where(
                    DocumentChunk.organization_id == organization_id,
                    DocumentChunk.content.ilike(f"%{query}%"),
                )
                if knowledge_base_ids:
                    stmt = stmt.where(DocumentChunk.knowledge_base_id.in_(knowledge_base_ids))
                stmt = stmt.limit(limit)
                result = await self.session.execute(stmt)
                return [row[0] for row in result.fetchall()]
        except Exception as exc:
            logger.debug(f"Lexical search skipped due to dialect or syntax error: {exc}")
            return []

    def _fuse_rankings(
        self,
        vector_ranks: list[UUID],
        lexical_ranks: list[UUID],
        vector_scores: dict[UUID, float],
        rrf_k: int = 60,
    ) -> list[tuple[UUID, float, str]]:
        """Combine vector and lexical ranks using Reciprocal Rank Fusion (RRF).

        Returns list of (chunk_id, fused_score, scoring_method).
        """
        all_ids = set(vector_ranks) | set(lexical_ranks)
        if not lexical_ranks:
            # Pure vector scoring
            return [(cid, vector_scores.get(cid, 0.0), "cosine_similarity") for cid in vector_ranks]

        fused_scores: dict[UUID, float] = {}
        for cid in all_ids:
            score = 0.0
            if cid in vector_ranks:
                rank_v = vector_ranks.index(cid) + 1
                score += 1.0 / (rrf_k + rank_v)
            if cid in lexical_ranks:
                rank_l = lexical_ranks.index(cid) + 1
                score += 1.0 / (rrf_k + rank_l)
            # Normalize RRF score to 0..1 range
            max_possible = 2.0 / (rrf_k + 1.0)
            fused_scores[cid] = min(1.0, score / max_possible)

        sorted_fused = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        return [(cid, score, "rrf_hybrid") for cid, score in sorted_fused]

    async def _verify_and_assemble_evidence(
        self,
        candidate_items: list[tuple[UUID, float, str]],
        organization_id: UUID,
        top_k: int,
    ) -> list[EvidenceItem]:
        """Verify candidate chunk IDs against authoritative PostgreSQL records.

        CRITICAL SECURITY INVARIANTS:
        1. Verifies knowledge_base is ACTIVE.
        2. Verifies document is ACTIVE (not soft deleted).
        3. Verifies chunk belongs to current_version_id (published active version).
        4. Verifies document_version processing_status is INDEXED.
        5. Rejects any chunk belonging to another organization.
        """
        chunk_map = {item[0]: (item[1], item[2]) for item in candidate_items}
        candidate_ids = list(chunk_map.keys())

        # Join DocumentChunk with parent Document, DocumentVersion, and KnowledgeBase
        stmt = (
            select(
                DocumentChunk,
                Document.title.label("document_title"),
                Document.lifecycle_status.label("doc_lifecycle"),
                Document.current_version_id.label("doc_current_version_id"),
                DocumentVersion.processing_status.label("version_status"),
                KnowledgeBase.status.label("kb_status"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
            .join(KnowledgeBase, KnowledgeBase.id == DocumentChunk.knowledge_base_id)
            .where(
                DocumentChunk.id.in_(candidate_ids),
                DocumentChunk.organization_id == organization_id,
                Document.organization_id == organization_id,
                DocumentVersion.organization_id == organization_id,
                KnowledgeBase.organization_id == organization_id,
            )
        )

        rows = (await self.session.execute(stmt)).all()
        verified_lookup: dict[UUID, Any] = {}

        for row in rows:
            chunk = row[0]
            doc_title = row.document_title
            doc_lifecycle = row.doc_lifecycle
            current_ver_id = row.doc_current_version_id
            ver_status = row.version_status
            kb_status = row.kb_status

            # INVARIANT CHECKS:
            # 1. Knowledge Base must be active
            if kb_status != KnowledgeBaseStatus.ACTIVE:
                continue
            # 2. Document must be active (not archived or deleted)
            if doc_lifecycle != DocumentLifecycleStatus.ACTIVE:
                continue
            # 3. Version must match the current active version of the document
            if chunk.version_id != current_ver_id:
                continue
            # 4. Version must be fully indexed
            if ver_status != DocumentProcessingStatus.INDEXED:
                continue

            verified_lookup[chunk.id] = (chunk, doc_title)

        # Assemble EvidenceItems in the ranked order
        evidence_list: list[EvidenceItem] = []
        rank = 1

        for cid, score, scoring_method in candidate_items:
            if cid not in verified_lookup:
                continue

            chunk, doc_title = verified_lookup[cid]
            headings: list[str] = (
                chunk.heading_hierarchy if isinstance(chunk.heading_hierarchy, list) else []
            )
            section_title = headings[-1] if headings else None

            evidence_item = EvidenceItem(
                evidence_id=f"ev_{rank}",
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_version_id=chunk.version_id,
                knowledge_base_id=chunk.knowledge_base_id,
                source_title=doc_title,
                section_title=section_title,
                heading_hierarchy=headings,
                relevant_excerpt=chunk.content,
                retrieval_rank=rank,
                retrieval_score=round(score, 4),
                scoring_method=scoring_method,
                citation_reference=f"[citation:{rank}]",
            )
            evidence_list.append(evidence_item)
            rank += 1
            if len(evidence_list) >= top_k:
                break

        return evidence_list
