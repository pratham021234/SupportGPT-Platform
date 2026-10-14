"""Message domain model representing individual communications within a conversation."""

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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import AuthorType, MessageDirection


class Message(Base, UUIDPrimaryKeyMixin):
    """Immutable individual communication record within a conversation thread."""

    __tablename__ = "messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Organization owning this message",
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Conversation thread containing this message",
    )
    direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Message transmission direction (inbound, outbound)",
    )
    author_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Author category (customer, agent, system, ai)",
    )
    author_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Author identifier (customer identity ID, agent ID, or system component)",
    )
    sender_display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Display name of the message sender",
    )
    body_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Plain text message body content",
    )
    body_rich: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Optional structured or formatted rich payload (e.g. HTML structure, cards)",
    )
    content_type: Mapped[str] = mapped_column(
        String(50),
        default="text/plain",
        nullable=False,
        comment="MIME content type of the primary body",
    )
    external_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Provider or protocol message identifier for idempotency (e.g. email Message-ID)",
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Deterministic secondary sequence ordering key within thread",
    )
    delivery_status: Mapped[str] = mapped_column(
        String(30),
        default="received",
        nullable=False,
        comment="Delivery lifecycle status (received, pending, sent, delivered, failed)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="UTC creation timestamp",
    )
    provider_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Upstream provider timestamp when message was sent or received",
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="Structured metadata associated with the message",
    )

    __table_args__ = (
        # Composite foreign key ensuring conversation and message share the identical organization
        ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["conversations.id", "conversations.organization_id"],
            name="fk_messages_conversation_org",
            ondelete="RESTRICT",
        ),
        # Unique constraint on (id, organization_id) for attachment composite foreign keys
        UniqueConstraint("id", "organization_id", name="uq_messages_id_organization_id"),
        # Deterministic chronological message query index
        Index("ix_messages_thread_order", "conversation_id", "created_at", "sequence_number"),
        # Index for external duplicate-delivery lookup
        Index("ix_messages_org_external_msg_id", "organization_id", "external_message_id"),
        CheckConstraint(
            f"direction IN ('{MessageDirection.INBOUND}', '{MessageDirection.OUTBOUND}')",
            name="ck_messages_valid_direction",
        ),
        CheckConstraint(
            f"author_type IN ('{AuthorType.CUSTOMER}', '{AuthorType.AGENT}', '{AuthorType.SYSTEM}', '{AuthorType.AI}')",
            name="ck_messages_valid_author_type",
        ),
        CheckConstraint("sequence_number >= 0", name="ck_messages_sequence_nonnegative"),
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, dir='{self.direction}', author='{self.author_type}')>"
