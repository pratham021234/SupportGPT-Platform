"""Verification run model representing an execution of the safety and policy verification pipeline."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RiskLevel, VerificationStatus


class VerificationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical model capturing a single verification pipeline execution on a draft version."""

    __tablename__ = "verification_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this verification run",
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("response_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent response draft evaluated in this run",
    )
    draft_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Exact version number of the draft evaluated",
    )
    verification_pipeline_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="v1.0.0",
        comment="Version of verification logic executed",
    )
    policy_set_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Monotonic version of the organization policy set applied",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=VerificationStatus.PASSED.value,
        index=True,
        comment="Outcome status (passed, passed_with_warnings, needs_revision, blocked, failed)",
    )
    risk_level: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=RiskLevel.LOW.value,
        index=True,
        comment="Assessed risk classification (low, medium, high, critical)",
    )
    requires_human_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether policy rules or risk level mandate explicit human review before send",
    )
    machine_readable_findings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Structured summary of claim findings, policy rule evaluations, and diagnostics",
    )
    evidence_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Snapshot of evidence items considered during this verification run",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when verification processing began",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when verification completed",
    )
    execution_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Total latency of the verification pipeline in milliseconds",
    )
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Correlation request ID",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Safe sanitized error description if verification failed or was blocked",
    )

    __table_args__ = (
        Index(
            "ix_verification_runs_org_draft_version",
            "organization_id",
            "draft_id",
            "draft_version",
        ),
        Index(
            "ix_verification_runs_org_status",
            "organization_id",
            "status",
        ),
    )
