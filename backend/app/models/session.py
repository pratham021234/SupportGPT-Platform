"""Authoritative user session model for server-side revocable session lifecycle."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserSession(Base):
    """Server-side session record enabling tracking, rotation, and immediate revocation."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the cryptographically random session token",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address recorded at session issuance",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Client User-Agent header recorded at session issuance",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Relationships
    user: Mapped["User"] = relationship(  # type: ignore[name-defined] # noqa: F821
        "User",
        back_populates="sessions",
        lazy="selectin",
    )

    @property
    def is_active(self) -> bool:
        """Check if session is currently valid and unrevoked."""
        now = datetime.now(UTC)
        # Handle timezone-naive timestamps if returned in testing environments
        expires = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=UTC)
        return self.revoked_at is None and expires > now

    def revoke(self) -> None:
        """Revoke this session immediately."""
        self.revoked_at = datetime.now(UTC)

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user_id={self.user_id} is_active={self.is_active}>"
