"""Pydantic request and response schemas for knowledge base and document APIs."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    """Payload to create a new organization knowledge collection."""

    name: str = Field(..., min_length=1, max_length=255, description="Collection name")
    description: str | None = Field(default=None, max_length=2000, description="Collection description")
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
