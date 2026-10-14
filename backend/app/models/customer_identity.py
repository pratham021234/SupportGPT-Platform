"""Customer identity contact methods model."""

import re
import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import IdentityType, IdentityVerificationStatus


def normalize_identity_value(identity_type: str, raw_val: str) -> str:
    """Apply deterministic canonical normalization rules to contact identities."""
    cleaned = raw_val.strip()
    if not cleaned:
        raise ValueError("Identity value cannot be empty or whitespace.")

    if identity_type == IdentityType.EMAIL:
        # Lowercase trimmed email
        return cleaned.lower()

    if identity_type == IdentityType.PHONE:
        # Standardize phone by removing formatting characters, preserving leading plus
        has_plus = cleaned.startswith("+")
        digits = re.sub(r"\D", "", cleaned)
        if not digits:
            raise ValueError("Phone number must contain digits.")
        return f"+{digits}" if has_plus else digits

    # General channels or provider-specific IDs: lowercase trimmed
    return cleaned.lower()


class CustomerIdentity(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Specific contact identifier (email, phone, channel handle) associated with a customer."""

    __tablename__ = "customer_identities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization scope for this identity",
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Customer owning this identity",
    )
    identity_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Identity category (email, phone, external_channel, provider_specific)",
    )
    normalized_value: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        comment="Canonical normalized value used for lookups and deduplication",
    )
    raw_value: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
        comment="Original unnormalized representation for display",
    )
    provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Optional channel or provider source identifier (e.g. slack, zendesk, smtp)",
    )
    verification_status: Mapped[str] = mapped_column(
        String(20),
        default=IdentityVerificationStatus.UNVERIFIED,
        nullable=False,
        comment="Verification state of this contact method",
    )

    __table_args__ = (
        # Composite foreign key ensuring customer and identity share the identical organization
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_identities_customer_org",
            ondelete="CASCADE",
        ),
        # Uniqueness scoped by organization and normalized identity to prevent collisions within tenant
        UniqueConstraint(
            "organization_id",
            "identity_type",
            "normalized_value",
            name="uq_customer_identities_org_type_val",
        ),
        Index("ix_customer_identities_lookup", "organization_id", "normalized_value"),
        CheckConstraint(
            f"identity_type IN ('{IdentityType.EMAIL}', '{IdentityType.PHONE}', '{IdentityType.EXTERNAL_CHANNEL}', '{IdentityType.PROVIDER_SPECIFIC}')",
            name="ck_customer_identities_valid_type",
        ),
        CheckConstraint(
            f"verification_status IN ('{IdentityVerificationStatus.UNVERIFIED}', '{IdentityVerificationStatus.VERIFIED}', '{IdentityVerificationStatus.REVOKED}')",
            name="ck_customer_identities_valid_verification",
        ),
    )

    def __repr__(self) -> str:
        return f"<CustomerIdentity(id={self.id}, type='{self.identity_type}', val='{self.normalized_value}')>"
