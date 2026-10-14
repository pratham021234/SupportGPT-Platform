"""Attachment domain model representing file metadata associated with messages."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AttachmentScanStatus


class Attachment(Base, UUIDPrimaryKeyMixin):
    """File metadata record attached to an individual message."""

    __tablename__ = "attachments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization scope for this attachment",
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Parent message containing this attachment",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Sanitized original filename as uploaded by client",
    )
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        comment="Opaque internal object-storage locator key (never public URL or raw client path)",
    )
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="MIME media type (e.g. application/pdf, image/png)",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="File size in bytes",
    )
    checksum_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Hex-encoded SHA-256 digest of stored bytes",
    )
    scan_status: Mapped[str] = mapped_column(
        String(20),
        default=AttachmentScanStatus.PENDING,
        nullable=False,
        comment="Antivirus / malware scan and readiness status",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC upload creation timestamp",
    )

    __table_args__ = (
        # Composite foreign key ensuring message and attachment share identical organization
        ForeignKeyConstraint(
            ["message_id", "organization_id"],
            ["messages.id", "messages.organization_id"],
            name="fk_attachments_message_org",
            ondelete="RESTRICT",
        ),
        Index("ix_attachments_org_message", "organization_id", "message_id"),
        CheckConstraint("size_bytes >= 0", name="ck_attachments_size_nonnegative"),
        CheckConstraint(
            f"scan_status IN ('{AttachmentScanStatus.PENDING}', '{AttachmentScanStatus.SCANNED_CLEAN}', '{AttachmentScanStatus.INFECTED}', '{AttachmentScanStatus.QUARANTINED}', '{AttachmentScanStatus.READY}')",
            name="ck_attachments_valid_scan_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Attachment(id={self.id}, filename='{self.filename}', bytes={self.size_bytes})>"
