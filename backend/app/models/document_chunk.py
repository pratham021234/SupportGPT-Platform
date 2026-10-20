"""Document chunk domain model representing reproducible text partitions for retrieval."""

import uuid

from sqlalchemy import (
    JSON,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Reproducible text chunk produced from a specific document version."""

    __tablename__ = "document_chunks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization owner of this chunk",
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Parent knowledge base",
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Parent document identity",
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Specific document version from which this chunk was derived",
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Zero-indexed or 1-indexed sequential chunk ordering within the version",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Normalized text content of this chunk",
    )
    word_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Word count in chunk content",
    )
    character_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Character length of chunk content",
    )
    start_char_idx: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Character start offset in the normalized version text",
    )
    end_char_idx: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Character end offset in the normalized version text",
    )
    heading_hierarchy: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=list,
        nullable=False,
        comment="Structural breadcrumbs/headings leading to this chunk",
    )
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 digest of normalized chunk text",
    )
    pipeline_version: Mapped[str] = mapped_column(
        String(50),
        default="1.0.0",
        nullable=False,
        comment="Chunker pipeline version that produced this record",
    )

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_document_chunks_id_org"),
        UniqueConstraint("version_id", "sequence_number", name="uq_document_chunks_ver_seq"),
        ForeignKeyConstraint(
            ["knowledge_base_id", "organization_id"],
            ["knowledge_bases.id", "knowledge_bases.organization_id"],
            name="fk_document_chunks_kb_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            name="fk_document_chunks_doc_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["version_id", "organization_id"],
            ["document_versions.id", "document_versions.organization_id"],
            name="fk_document_chunks_ver_org",
            ondelete="CASCADE",
        ),
        Index("ix_document_chunks_org_doc", "organization_id", "document_id"),
        Index("ix_document_chunks_org_ver", "organization_id", "version_id"),
        Index("ix_document_chunks_ver_seq", "version_id", "sequence_number"),
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, ver={self.version_id}, seq={self.sequence_number}, chars={self.character_count})>"
