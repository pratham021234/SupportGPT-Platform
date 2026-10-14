"""Conversation domain model representing interaction threads within a support ticket."""

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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ConversationStatus, TicketChannel


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Interaction communication thread belonging strictly to a ticket and organization."""

    __tablename__ = "conversations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization scope for this conversation thread",
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Parent support ticket for this thread",
    )
    channel_type: Mapped[str] = mapped_column(
        String(30),
        default=TicketChannel.EMAIL,
        nullable=False,
        comment="Channel medium for this specific thread (email, chat, api, web)",
    )
    external_thread_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="External thread or session identifier (e.g. email Message-ID/In-Reply-To or Slack thread_ts)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=ConversationStatus.ACTIVE,
        nullable=False,
        comment="Thread lifecycle status",
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of latest message appended to this thread",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="Structured metadata associated with the conversation thread",
    )

    __table_args__ = (
        # Composite foreign key enforcing that conversation cannot contradict parent ticket's organization
        ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_conversations_ticket_org",
            ondelete="RESTRICT",
        ),
        # Unique constraint on (id, organization_id) for message composite foreign keys
        UniqueConstraint("id", "organization_id", name="uq_conversations_id_organization_id"),
        Index("ix_conversations_org_ticket", "organization_id", "ticket_id"),
        Index("ix_conversations_org_external_thread", "organization_id", "external_thread_id"),
        CheckConstraint(
            f"status IN ('{ConversationStatus.ACTIVE}', '{ConversationStatus.PAUSED}', '{ConversationStatus.ARCHIVED}', '{ConversationStatus.CLOSED}')",
            name="ck_conversations_valid_status",
        ),
        CheckConstraint(
            f"channel_type IN ('{TicketChannel.EMAIL}', '{TicketChannel.CHAT}', '{TicketChannel.API}', '{TicketChannel.WEB}', '{TicketChannel.INTERNAL}')",
            name="ck_conversations_valid_channel_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, ticket_id={self.ticket_id}, status='{self.status}')>"
