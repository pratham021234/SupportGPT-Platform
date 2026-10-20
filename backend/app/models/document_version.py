"""Document version domain model representing an immutable file revision."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DocumentProcessingStatus


class DocumentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable revision of a document and its extracted/chunked state."""

    __tablename__ = "document_versions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization owner of this version",
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Parent document identity",
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Sequential version counter (1, 2, 3...)",
    )
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Opaque internal object storage locator key",
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original filename submitted for this revision",
    )
    media_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="MIME media type detected for this revision",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Binary size in bytes",
    )
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of the binary file",
    )
    processing_status: Mapped[str] = mapped_column(
        String(50),
        default=DocumentProcessingStatus.UPLOADED,
        nullable=False,
        comment="Active processing state (uploaded, queued, extracting, chunked, etc.)",
    )
    extractor_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Name of extractor that parsed the document text",
    )
    extractor_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Version of extractor component",
    )
    chunker_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Name of chunker algorithm used",
    )
    chunker_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Version of chunker algorithm",
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of text chunks generated for this version",
    )
    word_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total word count extracted from document",
    )
    character_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total character count extracted from document",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Error code if processing failed",
    )
    error_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Safe redacted failure summary",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of worker processing attempts",
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when next retry is scheduled",
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when current worker lease started",
    )
    locked_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Worker instance identifier holding the active lease",
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who uploaded this revision",
    )

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_document_versions_id_org"),
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_doc_ver"),
        ForeignKeyConstraint(
            ["document_id", "organization_id"],
            ["documents.id", "documents.organization_id"],
            name="fk_document_versions_doc_org",
            ondelete="CASCADE",
        ),
        Index("ix_document_versions_queue", "processing_status", "next_attempt_at", "created_at"),
        Index("ix_document_versions_org_doc", "organization_id", "document_id"),
    )

    def __repr__(self) -> str:
        return f"<DocumentVersion(id={self.id}, doc={self.document_id}, v={self.version_number}, status='{self.processing_status}')>"
