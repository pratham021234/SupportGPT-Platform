"""Claim finding model representing an individual atomic claim and its verification outcome."""

import uuid

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ClaimCategory, ClaimSupportStatus, ClaimVerificationMethod


class ClaimFinding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical model for an identified factual claim evaluated against retrieved evidence."""

    __tablename__ = "claim_findings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this claim finding",
    )
    verification_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("verification_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent verification run",
    )
    claim_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Exact text of the atomic claim extracted from the draft",
    )
    claim_category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ClaimCategory.GENERAL.value,
        comment="Category of the claim (policy, product_fact, pricing_refund, sla_commitment, general)",
    )
    support_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ClaimSupportStatus.SUPPORTED.value,
        index=True,
        comment="Grounding outcome (supported, partially_supported, unsupported, contradicted, not_verifiable)",
    )
    evidence_chunk_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="List of chunk IDs relevant to this claim",
    )
    confidence_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Documented confidence or similarity metric for this finding",
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Explicit rationale explaining why the claim is supported, unsupported, or contradicted",
    )
    verification_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ClaimVerificationMethod.EVIDENCE_GROUNDING.value,
        comment="Technique used to verify the claim",
    )

    __table_args__ = (
        Index(
            "ix_claim_findings_run_status",
            "verification_run_id",
            "support_status",
        ),
        Index(
            "ix_claim_findings_org_category",
            "organization_id",
            "claim_category",
        ),
    )
