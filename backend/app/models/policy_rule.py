"""Policy rule model representing organization-level response rules and compliance guardrails."""

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PolicyCategory, PolicyRuleType, PolicySeverity


class PolicyRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical model for an organization response policy rule and its configuration."""

    __tablename__ = "policy_rules"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant owning this policy rule",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Human-readable policy name",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="Explanation of the policy rule and rationale",
    )
    policy_category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PolicyCategory.FACTUAL_GROUNDING.value,
        index=True,
        comment="Category of policy (factual_grounding, prohibited_terms, mandatory_disclaimers, etc.)",
    )
    severity: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PolicySeverity.HIGH.value,
        comment="Severity assigned to violations of this policy (low, medium, high, critical)",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
        comment="Whether the policy is actively evaluated during verification runs",
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Monotonically increasing version number capturing policy modifications",
    )
    rule_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=PolicyRuleType.UNSUPPORTED_CLAIM_BLOCK.value,
        comment="Type of deterministic or semantic rule logic to apply",
    )
    rule_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Validated declarative configuration dictionary defining exact rule parameters",
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who created or last modified the policy",
    )

    __table_args__ = (
        CheckConstraint(
            "version_number >= 1",
            name="ck_policy_rules_version_positive",
        ),
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_policy_rules_org_name",
        ),
        Index(
            "ix_policy_rules_org_enabled",
            "organization_id",
            "is_enabled",
        ),
    )
