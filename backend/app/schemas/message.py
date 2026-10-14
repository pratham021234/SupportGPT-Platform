"""Pydantic schemas for messages within conversation threads."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AuthorType, MessageDirection


class MessageCreateRequest(BaseModel):
    """Payload to post a message into an existing conversation thread."""

    model_config = ConfigDict(extra="forbid")

    body_text: str = Field(..., min_length=1, max_length=65536, description="Plain text message content")
    body_rich: dict[str, Any] | None = Field(default=None, description="Optional structured formatted payload")
    content_type: str = Field(default="text/plain", max_length=50, description="MIME content type")
    direction: MessageDirection = Field(default=MessageDirection.OUTBOUND, description="Message transmission direction")
    author_type: AuthorType = Field(default=AuthorType.AGENT, description="Author classification category")
    external_message_id: str | None = Field(default=None, max_length=255, description="Upstream provider message ID for idempotency")


class MessageResponse(BaseModel):
    """Public representation of an individual message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    direction: MessageDirection
    author_type: AuthorType
    author_id: str | None = None
    sender_display_name: str | None = None
    body_text: str
    body_rich: dict[str, Any] | None = None
    content_type: str
    external_message_id: str | None = None
    sequence_number: int
    delivery_status: str
    created_at: datetime
    provider_sent_at: datetime | None = None


class MessageListResponse(BaseModel):
    """Paginated list of messages within a conversation."""

    items: list[MessageResponse]
    total: int
    limit: int
    offset: int
