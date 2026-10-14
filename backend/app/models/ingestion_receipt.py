"""Inbound event ingestion idempotency foundation model."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import IngestionStatus


class IngestionReceipt(Base, UUIDPrimaryKeyMixin):
    """Idempotency record tracking raw inbound external events from email, webhooks, or channels."""

    __tablename__ = "ingestion_receipts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization scope for this ingestion event",
    )
    source_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Provider or protocol source (e.g. sendgrid, postmark, twilio, custom_webhook)",
    )
    external_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="External event identifier supplied by provider for deduplication",
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Category of event (e.g. inbound_email, webhook_message, delivery_status)",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=IngestionStatus.RECEIVED,
        nullable=False,
        comment="Idempotency processing state (received, processing, processed, duplicate, failed, ignored)",
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC timestamp when the inbound event was registered",
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when processing completed or terminated",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Sanitized error classification code if processing failed",
    )
    error_summary: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="High-level non-sensitive summary of ingestion failure",
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Request correlation ID linking ingestion to gateway telemetry",
    )

    __table_args__ = (
        # Deduplication constraint: exactly one receipt per provider event within an organization
        UniqueConstraint(
            "organization_id",
            "source_provider",
            "external_event_id",
            name="uq_ingestion_receipts_provider_event",
        ),
        Index("ix_ingestion_receipts_org_status", "organization_id", "status"),
        CheckConstraint(
            f"status IN ('{IngestionStatus.RECEIVED}', '{IngestionStatus.PROCESSING}', '{IngestionStatus.PROCESSED}', '{IngestionStatus.DUPLICATE}', '{IngestionStatus.FAILED}', '{IngestionStatus.IGNORED}')",
            name="ck_ingestion_receipts_valid_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<IngestionReceipt(id={self.id}, provider='{self.source_provider}', event='{self.external_event_id}', status='{self.status}')>"
