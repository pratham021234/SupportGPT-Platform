"""Foundational system models for platform auditing, operational events, and baseline schema verification.

Full tenant organizations, user memberships, and conversation schemas are scheduled for Phase 02/03.
"""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SystemEventLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authoritative platform system event and audit record.

    Records critical platform lifecycle events such as migration completion,
    health transitions, and configuration reloads.
    """

    __tablename__ = "system_event_logs"

    event_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Machine-readable system event identifier",
    )
    component: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Platform component emitting the event (e.g. backend, database, queue)",
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Structured metadata associated with the event",
    )

    def __repr__(self) -> str:
        return f"<SystemEventLog(id={self.id}, event='{self.event_name}', component='{self.component}')>"
