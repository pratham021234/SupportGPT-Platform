"""AI Operation Trace model capturing execution spans, latencies, tokens, and outcomes."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import TraceOutcome


class AIOperationTrace(Base, UUIDPrimaryKeyMixin):
    """Canonical execution trace representing a single end-to-end AI workflow."""

    __tablename__ = "ai_operation_traces"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this operation trace",
    )
    trace_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Unique correlation trace ID spanning this operation",
    )
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Associated HTTP request correlation ID (X-Request-ID)",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User initiating the request or None for background/system operations",
    )
    operation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Type of AI operation (rag_query, answer_generation, response_verification, etc.)",
    )
    entity_type: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Associated target entity type (ticket, response_draft, document)",
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Associated target entity ID",
    )
    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="system",
        comment="AI or infrastructure provider invoked (fastembed, openai, deterministic, system)",
    )
    model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="none",
        comment="Model identifier invoked",
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when operation execution began",
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when operation execution completed",
    )
    duration_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Total elapsed execution duration in milliseconds",
    )
    outcome: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TraceOutcome.SUCCESS.value,
        index=True,
        comment="Final outcome (success, failure, abstained, blocked)",
    )
    error_category: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Normalized failure category if outcome was failure/blocked",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Sanitized error description or abstention reason",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of internal retry attempts executed",
    )
    evidence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of evidence chunks retrieved or evaluated",
    )
    token_usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=dict,
        comment="Granular token consumption counts (input, output, embedding)",
    )
    estimated_cost_usd: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Calculated estimated cost in USD based on pricing tier",
    )
    pipeline_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Active pipeline version used during this execution",
    )
    policy_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Active policy version used during this execution",
    )
    spans: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=list,
        comment="Granular execution spans (stage name, timing, outcome, references)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="Audit creation timestamp",
    )

    __table_args__ = (
        Index(
            "ix_ai_operation_traces_org_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_ai_operation_traces_org_op_outcome",
            "organization_id",
            "operation_type",
            "outcome",
        ),
    )
