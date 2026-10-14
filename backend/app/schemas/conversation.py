"""Pydantic schemas for conversation threads."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ConversationStatus, TicketChannel


class ConversationCreateRequest(BaseModel):
    """Payload to create an additional conversation thread on a ticket."""

    model_config = ConfigDict(extra="forbid")

    channel_type: TicketChannel = Field(default=TicketChannel.EMAIL, description="Medium for thread")
    external_thread_id: str | None = Field(default=None, max_length=255, description="External thread ID")


class ConversationResponse(BaseModel):
    """Public representation of a conversation thread."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    ticket_id: uuid.UUID
    channel_type: TicketChannel
    external_thread_id: str | None = None
    status: ConversationStatus
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """List of conversations belonging to a ticket."""

    items: list[ConversationResponse]
    total: int
