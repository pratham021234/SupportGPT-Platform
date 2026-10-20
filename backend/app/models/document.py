"""Document canonical model representing a source file within a knowledge base."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
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
from app.models.enums import (
    DocumentLifecycleStatus,
    DocumentProcessingStatus,
    DocumentSourceType,
)


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical document record managed within a knowledge base."""

    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization owner of this document",
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Parent knowledge base collection",
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Display title of the document",
    )
    source_type: Mapped[str] = mapped_column(
        String(50),
        default=DocumentSourceType.FILE_UPLOAD,
        nullable=False,
        comment="Source origin (file_upload, manual_entry, api)",
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Sanitized original filename as uploaded",
    )
    media_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Verified MIME media type (e.g. application/pdf, text/markdown)",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        default=DocumentProcessingStatus.UPLOADED,
        nullable=False,
        comment="Processing pipeline state of the active version",
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(20),
        default=DocumentLifecycleStatus.ACTIVE,
        nullable=False,
        comment="Lifecycle state (active, archived, deleted)",
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Foreign key identifier of the currently published usable version",
    )
    current_version_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Monotonic version number of the active revision",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="Byte size of the current version binary object",
    )
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 cryptographic digest of the source binary file",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Safe error classification code if processing failed",
    )
    error_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Redacted error summary for operator inspection",
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created the document",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when document was soft deleted",
    )

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_documents_id_org"),
        ForeignKeyConstraint(
            ["knowledge_base_id", "organization_id"],
            ["knowledge_bases.id", "knowledge_bases.organization_id"],
            name="fk_documents_kb_org",
            ondelete="CASCADE",
        ),
        Index("ix_documents_org_kb", "organization_id", "knowledge_base_id"),
        Index("ix_documents_org_status", "organization_id", "status"),
        Index("ix_documents_org_lifecycle", "organization_id", "lifecycle_status"),
        CheckConstraint(
            f"lifecycle_status IN ('{DocumentLifecycleStatus.ACTIVE}', '{DocumentLifecycleStatus.ARCHIVED}', '{DocumentLifecycleStatus.DELETED}')",
            name="ck_documents_lifecycle_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, title='{self.title}', status='{self.status}', v={self.current_version_number})>"
