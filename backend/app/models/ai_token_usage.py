"""AI Token Usage model for granular usage accounting, pricing calculation, and auditing."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AITokenUsageRecord(Base, UUIDPrimaryKeyMixin):
    """Canonical model tracking token consumption and cost per operation."""

    __tablename__ = "ai_token_usages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant consuming the AI tokens",
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Associated execution trace ID",
    )
    operation_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="AI operation consuming tokens (rag_query, answer_generation, verification, etc.)",
    )
    provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Provider utilized (fastembed, openai, deterministic)",
    )
    model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Model utilized",
    )
    input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of prompt or input tokens",
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of generated completion tokens",
    )
    embedding_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of text tokens embedded into vectors",
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sum total of input, output, and embedding tokens",
    )
    is_provider_reported: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if directly reported by the provider API; False if locally estimated",
    )
    estimated_cost_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Estimated monetary cost in USD according to the active pricing tier",
    )
    pricing_tier: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="standard",
        comment="Pricing catalog tier applied (e.g., openai-2026-q1, local-onnx-free)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="Consumption timestamp",
    )

    __table_args__ = (
        Index(
            "ix_ai_token_usages_org_created",
            "organization_id",
            "created_at",
        ),
        Index(
            "ix_ai_token_usages_org_provider_model",
            "organization_id",
            "provider",
            "model",
        ),
    )
