"""Evaluation Run model for persisting repeatable RAG & verification quality evaluations."""

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
from app.models.enums import EvaluationStatus


class EvaluationRunRecord(Base, UUIDPrimaryKeyMixin):
    """Canonical model persisting an execution of the evaluation benchmark on a dataset."""

    __tablename__ = "evaluation_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this evaluation run",
    )
    dataset_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="enterprise_eval_dataset_v1",
        comment="Identifier of the evaluated benchmark dataset",
    )
    dataset_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="v1.0",
        comment="Version tag of the evaluated dataset",
    )
    total_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total test queries evaluated",
    )
    answerable_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of queries with expected ground truth answers",
    )
    unanswerable_cases: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of queries expected to trigger abstention",
    )
    embedding_provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Embedding provider evaluated (fastembed, openai)",
    )
    embedding_model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Embedding model evaluated",
    )
    generation_provider: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Generation provider evaluated",
    )
    generation_model: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Generation model evaluated",
    )
    retrieval_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=dict,
        comment="Snapshot of retrieval parameters (top_k, score_threshold, hybrid_search)",
    )
    verification_pipeline_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Verification pipeline version active during evaluation",
    )
    policy_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Policy set version active during evaluation",
    )
    mean_recall_at_k: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Measured Recall@k across answerable evaluation queries",
    )
    mean_reciprocal_rank: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Measured Mean Reciprocal Rank (MRR)",
    )
    citation_validity_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Fraction of generated citations pointing to authorized evidence",
    )
    abstention_accuracy: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Fraction of unanswerable queries correctly abstained from",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=EvaluationStatus.COMPLETED.value,
        index=True,
        comment="Execution status (running, completed, failed)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Sanitized error description if evaluation failed",
    )
    case_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=list,
        comment="Granular per-query evaluation findings and metrics",
    )
    regressions: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        nullable=False,
        default=dict,
        comment="Regression analysis comparison against baseline run",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
        comment="Run initiation timestamp",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Run completion timestamp",
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Engineer initiating the evaluation run",
    )

    __table_args__ = (
        Index(
            "ix_evaluation_runs_org_created",
            "organization_id",
            "created_at",
        ),
    )
