"""Authoritative user account domain model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import UserStatus


class User(Base, TimestampMixin):
    """User account model for authentication, identity, and organization membership."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    status: Mapped[UserStatus] = mapped_column(
        String(30),
        default=UserStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    memberships: Mapped[list["OrganizationMembership"]] = relationship(  # type: ignore[name-defined] # noqa: F821
        "OrganizationMembership",
        foreign_keys="[OrganizationMembership.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    sessions: Mapped[list["UserSession"]] = relationship(  # type: ignore[name-defined] # noqa: F821
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def is_active(self) -> bool:
        """Evaluate if user account is allowed to authenticate and access platform."""
        return self.status == UserStatus.ACTIVE

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} status={self.status}>"
