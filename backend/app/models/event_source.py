"""External event source configuration model."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SourceProvider, SourceStatus


class EventSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """External provider event source configuration scoped to an organization."""

    __tablename__ = "event_sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization scope for this external source",
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        default=SourceProvider.GENERIC_WEBHOOK,
        nullable=False,
        comment="Provider type (generic_webhook, custom_api, email_postmark, etc.)",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Human-readable label for this integration source",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=SourceStatus.ACTIVE,
        nullable=False,
        comment="Source connection state (active, inactive, revoked)",
    )
    external_account_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="External installation, project, or account ID",
    )
    signing_secret_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Cryptographic hash of the signing secret for integrity verification",
    )
    signing_secret_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted signing secret ciphertext stored securely at rest",
    )
    secret_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Managed secret reference URI (e.g. env:WH_SEC or vault:path)",
    )
    signing_secret_preview: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Masked preview of the secret for operator display (e.g. whsec_...****)",
    )
    supported_event_types: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=lambda: ["ticket.created", "ticket.updated", "message.received"],
        nullable=False,
        comment="JSON array of event types allowed for this source",
    )
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp of the most recent event received from this source",
    )

    # Relationships
    organization = relationship("Organization")
    receipts = relationship("IngestionReceipt", back_populates="source", cascade="all")

    __table_args__ = (
        Index("ix_event_sources_org_provider", "organization_id", "provider"),
        CheckConstraint(
            f"status IN ('{SourceStatus.ACTIVE}', '{SourceStatus.INACTIVE}', '{SourceStatus.REVOKED}')",
            name="ck_event_sources_valid_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<EventSource(id={self.id}, org={self.organization_id}, provider='{self.provider}', name='{self.name}', status='{self.status}')>"
