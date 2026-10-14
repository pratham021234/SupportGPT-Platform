"""Ticket domain model representing canonical support cases."""

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
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TicketChannel, TicketPriority, TicketStatus


class Ticket(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Canonical support case record scoped strictly to an organization."""

    __tablename__ = "tickets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization owning this support ticket",
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Optional customer initiating or associated with the ticket",
    )
    ticket_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Sequential human-readable ticket number allocated per organization",
    )
    ticket_reference: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Formatted public ticket reference code (e.g. TICK-1001)",
    )
    subject: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Summary headline of the support request",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default=TicketStatus.OPEN,
        nullable=False,
        comment="Operational ticket status",
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        default=TicketPriority.MEDIUM,
        nullable=False,
        comment="Ticket urgency / priority tier",
    )
    channel: Mapped[str] = mapped_column(
        String(30),
        default=TicketChannel.EMAIL,
        nullable=False,
        comment="Initial ingestion channel for the ticket",
    )
    assigned_actor_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Assigned agent or system actor identifier without premature user table coupling",
    )
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of first outbound agent/system reply",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when ticket status transitioned to resolved",
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when ticket status transitioned to closed",
    )
    external_reference: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional source reference ID from external ticketing systems",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="Structured metadata associated with the ticket",
    )

    __table_args__ = (
        # Composite foreign key ensuring customer belongs to the identical organization if set
        ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_tickets_customer_org",
            ondelete="SET NULL",
        ),
        # Unique constraints
        UniqueConstraint("id", "organization_id", name="uq_tickets_id_organization_id"),
        UniqueConstraint("organization_id", "ticket_number", name="uq_tickets_org_ticket_number"),
        UniqueConstraint(
            "organization_id", "ticket_reference", name="uq_tickets_org_ticket_reference"
        ),
        # Indexes for query patterns
        Index("ix_tickets_org_status", "organization_id", "status"),
        Index("ix_tickets_org_priority", "organization_id", "priority"),
        Index("ix_tickets_org_created_at", "organization_id", "created_at"),
        # Integrity check constraints
        CheckConstraint("ticket_number > 0", name="ck_tickets_ticket_number_positive"),
        CheckConstraint(
            f"status IN ('{TicketStatus.OPEN}', '{TicketStatus.PENDING}', '{TicketStatus.IN_PROGRESS}', '{TicketStatus.RESOLVED}', '{TicketStatus.CLOSED}')",
            name="ck_tickets_valid_status",
        ),
        CheckConstraint(
            f"priority IN ('{TicketPriority.URGENT}', '{TicketPriority.HIGH}', '{TicketPriority.MEDIUM}', '{TicketPriority.LOW}')",
            name="ck_tickets_valid_priority",
        ),
        CheckConstraint(
            f"channel IN ('{TicketChannel.EMAIL}', '{TicketChannel.CHAT}', '{TicketChannel.API}', '{TicketChannel.WEB}', '{TicketChannel.INTERNAL}')",
            name="ck_tickets_valid_channel",
        ),
    )

    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, ref='{self.ticket_reference}', status='{self.status}')>"
