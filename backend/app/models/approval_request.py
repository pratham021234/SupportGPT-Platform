"""Approval request model representing human-in-the-loop governance for response drafts."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ApprovalStatus, MembershipRole


class ApprovalRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical model capturing human approval requests, reviewer assignments, and decisions."""

    __tablename__ = "approval_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this approval request",
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("response_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent response draft requiring approval",
    )
    draft_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Exact version number of the draft under review",
    )
    verification_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Associated verification run whose findings inform the review",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ApprovalStatus.PENDING.value,
        index=True,
        comment="Current approval lifecycle status (pending, approved, rejected, revision_requested, invalidated, cancelled)",
    )
    required_role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=MembershipRole.AGENT.value,
        comment="Minimum organization role required to review and decide this request",
    )
    separation_of_duties: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="If True, the requester cannot approve their own draft",
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who submitted the draft for approval",
    )
    decision_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who approved, rejected, or requested revision",
    )
    decision_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Mandatory or optional rationale provided by the approver",
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the decision was committed",
    )

    __table_args__ = (
        Index(
            "ix_approval_requests_org_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_approval_requests_org_draft_version",
            "organization_id",
            "draft_id",
            "draft_version",
        ),
    )
