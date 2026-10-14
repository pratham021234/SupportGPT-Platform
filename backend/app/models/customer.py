"""Customer domain model representing external persons or businesses contacting support."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CustomerStatus


class Customer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """External customer record scoped strictly to an organization."""

    __tablename__ = "customers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization owning this customer record",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable customer name",
    )
    company_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional customer organization or business affiliation",
    )
    external_customer_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional identifier from external CRM or customer datastore",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=CustomerStatus.ACTIVE,
        nullable=False,
        comment="Customer lifecycle state",
    )

    __table_args__ = (
        # Ensure composite uniqueness for tenant-boundary composite foreign keys
        UniqueConstraint("id", "organization_id", name="uq_customers_id_organization_id"),
        Index("ix_customers_org_external_id", "organization_id", "external_customer_id"),
        Index("ix_customers_org_status", "organization_id", "status"),
        CheckConstraint(
            f"status IN ('{CustomerStatus.ACTIVE}', '{CustomerStatus.BLOCKED}', '{CustomerStatus.MERGED}')",
            name="ck_customers_valid_status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Customer(id={self.id}, name='{self.display_name}', org_id={self.organization_id})>"
        )
