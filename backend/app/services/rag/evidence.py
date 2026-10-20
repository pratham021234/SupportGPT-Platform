"""Evidence and Citation Data Models.

Defines typed, immutable representations for retrieved knowledge chunks,
structural section breadcrumbs, server-generated citation markers, and scoring metadata.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """Authoritative evidence chunk retrieved and validated for ground truth."""

    evidence_id: str = Field(..., description="Stable server-generated identifier, e.g. 'ev_1'")
    chunk_id: UUID = Field(..., description="Canonical PostgreSQL document_chunk UUID")
    document_id: UUID = Field(..., description="Parent document UUID")
    document_version_id: UUID = Field(..., description="Document version UUID that generated this chunk")
    knowledge_base_id: UUID = Field(..., description="Knowledge base UUID")
    source_title: str = Field(..., description="Display title of the source document")
    section_title: str | None = Field(default=None, description="Structural heading or section title if present")
    heading_hierarchy: list[str] = Field(default_factory=list, description="Section breadcrumbs leading to this chunk")
    relevant_excerpt: str = Field(..., description="Exact normalized text excerpt from authoritative database record")
    retrieval_rank: int = Field(..., ge=1, description="1-based ranking in retrieval results")
    retrieval_score: float = Field(..., ge=0.0, le=1.0, description="Normalized similarity or fusion score")
    scoring_method: str = Field(default="cosine_similarity", description="Scoring mechanism: cosine_similarity or rrf_hybrid")
    citation_reference: str = Field(..., description="Server-generated citation token, e.g. '[citation:1]'")


class CitationItem(BaseModel):
    """Validated citation linking an answer claim back to authoritative evidence."""

    citation_number: int = Field(..., ge=1, description="Sequential citation index")
    citation_marker: str = Field(..., description="Exact marker embedded in answer, e.g. '[citation:1]'")
    evidence_id: str = Field(..., description="Matching evidence item identifier")
    chunk_id: UUID = Field(..., description="Source document chunk UUID")
    document_id: UUID = Field(..., description="Source document UUID")
    source_title: str = Field(..., description="Source document title")
    section_title: str | None = Field(default=None, description="Source section title if present")
    excerpt: str = Field(..., description="Source excerpt supporting this citation")
    retrieval_score: float = Field(..., description="Relevance score of supporting evidence")


class GroundedAnswerResult(BaseModel):
    """Complete grounded answer container with verified citations and provenance."""

    question: str = Field(..., description="Original user question")
    answer: str = Field(..., description="Evidence-grounded answer text with embedded citation markers")
    citations: list[CitationItem] = Field(default_factory=list, description="Validated citations referencing evidence")
    evidence: list[EvidenceItem] = Field(default_factory=list, description="Authoritative evidence items used for grounding")
    abstention_status: bool = Field(default=False, description="True if system abstained due to insufficient evidence")
    abstention_reason: str | None = Field(default=None, description="Classification reason for abstention")
    model_name: str | None = Field(default=None, description="Model used for answer generation")
    retrieval_latency_ms: float = Field(default=0.0, description="Retrieval execution time in milliseconds")
    generation_latency_ms: float = Field(default=0.0, description="Answer generation execution time in milliseconds")
    total_latency_ms: float = Field(default=0.0, description="Total end-to-end latency in milliseconds")
