"""Ticket event lifecycle audit history domain model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AuthorType


class TicketEvent(Base, UUIDPrimaryKeyMixin):
    """Append-only historical audit record capturing lifecycle mutations on tickets."""

    __tablename__ = "ticket_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization scope for this lifecycle event",
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Ticket subject of the lifecycle event",
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Domain event category (e.g. created, status_changed, priority_changed)",
    )
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC timestamp when the event occurred",
    )
    actor_type: Mapped[str] = mapped_column(
        String(20),
        default=AuthorType.SYSTEM,
        nullable=False,
        comment="Actor initiating the mutation (customer, agent, system, ai)",
    )
    actor_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Identifier of the executing actor",
    )
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="State representation prior to mutation",
    )
    new_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="State representation subsequent to mutation",
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Contextual structured payload explaining the event",
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Request correlation ID linking the mutation to an HTTP trace",
    )

    __table_args__ = (
        # Composite foreign key ensuring ticket and event share identical organization
        ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_ticket_events_ticket_org",
            ondelete="RESTRICT",
        ),
        Index("ix_ticket_events_ticket_order", "ticket_id", "event_timestamp"),
        CheckConstraint(
            f"actor_type IN ('{AuthorType.CUSTOMER}', '{AuthorType.AGENT}', '{AuthorType.SYSTEM}', '{AuthorType.AI}')",
            name="ck_ticket_events_valid_actor_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<TicketEvent(id={self.id}, ticket_id={self.ticket_id}, type='{self.event_type}')>"
