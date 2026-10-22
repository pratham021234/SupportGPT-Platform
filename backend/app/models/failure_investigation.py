"""Failure Investigation model for auditable incident review, deduplication, and resolution."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import FailureCategory, InvestigationStatus, RiskLevel


class FailureInvestigation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical model representing an operational failure investigation."""

    __tablename__ = "failure_investigations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this failure investigation",
    )
    investigation_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
        comment="Human-readable investigation identifier (e.g., INV-0001)",
    )
    fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Deterministic SHA-256 grouping key for automated failure deduplication",
    )
    failure_category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=FailureCategory.UNKNOWN_ERROR.value,
        index=True,
        comment="Categorized root domain of the failure",
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RiskLevel.MEDIUM.value,
        index=True,
        comment="Assessed operational severity (low, medium, high, critical)",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=InvestigationStatus.OPEN.value,
        index=True,
        comment="Investigation lifecycle state (open, investigating, resolved, ignored)",
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Most recent execution trace ID where this failure occurred",
    )
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Correlation request ID associated with the failure",
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Target domain entity type affected (e.g., ticket, draft, document)",
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Target domain entity ID affected",
    )
    provider: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="External or internal provider involved in the failure",
    )
    sanitized_error_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Redacted, safe description of the error observed",
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Timestamp when this failure fingerprint was first observed",
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Timestamp when this failure fingerprint was most recently observed",
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Number of times this failure fingerprint has recurred",
    )
    pipeline_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Active pipeline version during failure",
    )
    diagnostic_hypotheses: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=list,
        comment="Structured diagnostic hypotheses and recommended remediation actions",
    )
    resolution_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Operator notes explaining root cause and resolution steps",
    )
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Investigating engineer assigned to this failure record",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when this investigation was marked resolved",
    )

    __table_args__ = (
        Index(
            "ix_failure_investigations_org_fingerprint",
            "organization_id",
            "fingerprint",
        ),
        Index(
            "ix_failure_investigations_org_status_severity",
            "organization_id",
            "status",
            "severity",
        ),
    )
