"""Normalized canonical event schemas for SupportGPT ingestion pipeline."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AuthorType, MessageDirection, TicketPriority


class CanonicalCustomer(BaseModel):
    """Normalized external customer identity details."""

    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=150)
    external_id: str | None = Field(default=None, max_length=255)


class CanonicalEvent(BaseModel):
    """Authoritative normalized event representation decoupled from external provider wire formats."""

    model_config = ConfigDict(extra="ignore")

    schema_version: str = Field(default="1.0", description="Canonical event schema version")
    source_id: uuid.UUID | None = Field(
        default=None, description="Internal EventSource UUID if known"
    )
    provider: str = Field(
        ..., max_length=50, description="Originating provider (e.g. generic_webhook, custom_api)"
    )
    external_event_id: str = Field(
        ..., min_length=1, max_length=255, description="Unique event identifier from provider"
    )
    event_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Normalized event type (ticket.created, message.received, etc.)",
    )
    event_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="UTC timestamp of the original event"
    )
    external_ticket_id: str | None = Field(
        default=None, max_length=255, description="External ticket, issue, or conversation ID"
    )
    external_conversation_id: str | None = Field(
        default=None, max_length=255, description="External thread or session ID"
    )
    external_message_id: str | None = Field(
        default=None, max_length=255, description="External message ID for idempotency"
    )
    subject: str | None = Field(
        default=None, max_length=255, description="Ticket or thread subject"
    )
    message_body: str | None = Field(default=None, description="Message body or ticket description")
    message_direction: MessageDirection = Field(default=MessageDirection.INBOUND)
    author_type: AuthorType = Field(default=AuthorType.CUSTOMER)
    customer: CanonicalCustomer | None = Field(
        default=None, description="Identified or claimed external customer"
    )
    priority: TicketPriority | None = Field(
        default=None, description="Optional ticket priority override"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Safe arbitrary correlation metadata"
    )
    correlation_id: str | None = Field(default=None, max_length=100)
