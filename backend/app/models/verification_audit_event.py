"""Verification audit event model representing append-only governance trails."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class VerificationAuditEvent(Base, UUIDPrimaryKeyMixin):
    """Append-only audit trail capturing every significant verification and approval event."""

    __tablename__ = "verification_audit_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this audit event",
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Type of workflow event (draft_created, verification_completed, approval_granted, etc.)",
    )
    entity_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Category of affected entity (draft, verification_run, policy, approval_request)",
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Primary key of the affected entity",
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User ID responsible for the event, or null for system events",
    )
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Correlation trace ID",
    )
    event_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable summary of the auditable action",
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Structured context containing version numbers, rule triggers, or decision notes",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Immutable UTC creation timestamp",
    )

    __table_args__ = (
        Index(
            "ix_verification_audit_org_event",
            "organization_id",
            "event_type",
        ),
        Index(
            "ix_verification_audit_org_entity",
            "organization_id",
            "entity_type",
            "entity_id",
        ),
    )
