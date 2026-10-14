"""Authoritative organization membership domain model."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import MembershipRole, MembershipStatus


class OrganizationMembership(Base, TimestampMixin):
    """Associative entity linking users to organizations with explicit roles and lifecycle state."""

    __tablename__ = "organization_memberships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MembershipRole] = mapped_column(
        String(30),
        default=MembershipRole.AGENT,
        nullable=False,
        index=True,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        String(30),
        default=MembershipStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Database-level constraints
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_memberships_org_user",
        ),
        CheckConstraint(
            f"role IN ('{MembershipRole.OWNER}', '{MembershipRole.ADMIN}', '{MembershipRole.AGENT}', '{MembershipRole.VIEWER}')",
            name="ck_organization_memberships_valid_role",
        ),
        CheckConstraint(
            f"status IN ('{MembershipStatus.ACTIVE}', '{MembershipStatus.SUSPENDED}', '{MembershipStatus.INVITED}', '{MembershipStatus.REVOKED}')",
            name="ck_organization_memberships_valid_status",
        ),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined] # noqa: F821
        "Organization",
        lazy="selectin",
    )
    user: Mapped["User"] = relationship(  # type: ignore[name-defined] # noqa: F821
        "User",
        foreign_keys=[user_id],
        back_populates="memberships",
        lazy="selectin",
    )
    inviter: Mapped["User | None"] = relationship(  # type: ignore[name-defined] # noqa: F821
        "User",
        foreign_keys=[invited_by_user_id],
        lazy="selectin",
    )

    @property
    def is_active(self) -> bool:
        """Evaluate if membership grants active operational access to the organization."""
        return self.status == MembershipStatus.ACTIVE

    def __repr__(self) -> str:
        return (
            f"<OrganizationMembership id={self.id} org_id={self.organization_id} "
            f"user_id={self.user_id} role={self.role} status={self.status}>"
        )
