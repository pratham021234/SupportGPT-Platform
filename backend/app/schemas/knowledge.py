"""Pydantic request and response schemas for knowledge base and document APIs."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    """Payload to create a new organization knowledge collection."""

    name: str = Field(..., min_length=1, max_length=255, description="Collection name")
    description: str | None = Field(
        default=None, max_length=2000, description="Collection description"
    )
    config: dict = Field(default_factory=dict, description="Processing configuration")


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base collection response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    status: str
    config: dict
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListResponse(BaseModel):
    """Paginated list of knowledge bases."""

    items: list[KnowledgeBaseResponse]
    total: int


class DocumentVersionResponse(BaseModel):
    """Immutable document version response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    document_id: uuid.UUID
    version_number: int
    original_filename: str
    media_type: str
    size_bytes: int
    checksum: str
    processing_status: str
    extractor_name: str | None
    extractor_version: str | None
    chunker_name: str | None
    chunker_version: str | None
    chunk_count: int
    word_count: int
    character_count: int
    error_code: str | None
    error_summary: str | None
    attempt_count: int
    created_at: datetime


class DocumentResponse(BaseModel):
    """Canonical document record response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    title: str
    source_type: str
    original_filename: str
    media_type: str
    status: str
    lifecycle_status: str
    current_version_id: uuid.UUID | None
    current_version_number: int
    size_bytes: int
    checksum: str
    error_code: str | None
    error_summary: str | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    """Response returned upon successful document upload and staging."""

    document: DocumentResponse
    version: DocumentVersionResponse


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: list[DocumentResponse]
    total: int


class DocumentChunkResponse(BaseModel):
    """Reproducible text chunk response with provenance metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    sequence_number: int
    content: str
    word_count: int
    character_count: int
    start_char_idx: int
    end_char_idx: int
    heading_hierarchy: list[str]
    checksum: str
    pipeline_version: str
    created_at: datetime


class DocumentChunkListResponse(BaseModel):
    """List of persisted chunks for a document version."""

    items: list[DocumentChunkResponse]
    total: int


class KnowledgeSearchRequest(BaseModel):
    """Search request against organization knowledge base collections."""

    query: str = Field(..., min_length=2, max_length=2000, description="Search query string")
    top_k: int = Field(
        default=5, ge=1, le=20, description="Maximum number of evidence chunks to retrieve"
    )
    min_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Minimum relevance score threshold"
    )
    enable_hybrid: bool = Field(default=True, description="Enable hybrid vector + full-text search")


class EvidenceItemResponse(BaseModel):
    """Verified evidence item response container."""

    evidence_id: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    source_title: str
    section_title: str | None
    heading_hierarchy: list[str]
    relevant_excerpt: str
    retrieval_rank: int
    retrieval_score: float
    scoring_method: str
    citation_reference: str


class KnowledgeSearchResponse(BaseModel):
    """Search response with ranked evidence and latency diagnostics."""

    query: str
    evidence: list[EvidenceItemResponse]
    total_results: int
    retrieval_latency_ms: float


class KnowledgeAnswerRequest(BaseModel):
    """Knowledge-grounded question answering request."""

    question: str = Field(..., min_length=2, max_length=2000, description="User question to answer")
    top_k: int = Field(default=5, ge=1, le=20, description="Maximum evidence items to use")
    min_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Minimum relevance score threshold"
    )
    enable_hybrid: bool = Field(default=True, description="Enable hybrid vector + full-text search")


class CitationResponse(BaseModel):
    """Verified citation item response."""

    citation_number: int
    citation_marker: str
    evidence_id: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    source_title: str
    section_title: str | None
    excerpt: str
    retrieval_score: float


class KnowledgeAnswerResponse(BaseModel):
    """Grounded answer response with verified citations and provenance."""

    question: str
    answer: str
    citations: list[CitationResponse]
    evidence: list[EvidenceItemResponse]
    abstention_status: bool
    abstention_reason: str | None
    model_name: str | None
    retrieval_latency_ms: float
    generation_latency_ms: float
    total_latency_ms: float
