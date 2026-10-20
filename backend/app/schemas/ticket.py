"""Pydantic schemas for tickets and ticket lifecycle events."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TicketChannel, TicketPriority, TicketStatus


class TicketCreateRequest(BaseModel):
    """Payload to create a support ticket with optional initial message thread."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(
        ..., min_length=1, max_length=500, description="Summary headline of support request"
    )
    description: str | None = Field(
        default=None, max_length=65536, description="Initial conversation message body"
    )
    priority: TicketPriority = Field(
        default=TicketPriority.MEDIUM, description="Initial ticket priority tier"
    )
    channel: TicketChannel = Field(
        default=TicketChannel.EMAIL, description="Ingestion or origin channel"
    )
    customer_id: uuid.UUID | None = Field(
        default=None, description="Optional existing customer identifier"
    )
    assigned_actor_id: str | None = Field(
        default=None, max_length=100, description="Optional agent or actor ID to assign"
    )
    external_reference: str | None = Field(
        default=None, max_length=255, description="Optional external CRM/ticket ID"
    )


class TicketUpdateRequest(BaseModel):
    """Payload to update mutable ticket attributes under optimistic concurrency control."""

    model_config = ConfigDict(extra="forbid")

    subject: str | None = Field(
        default=None, min_length=1, max_length=500, description="Updated ticket headline"
    )
    status: TicketStatus | None = Field(default=None, description="Target lifecycle status")
    priority: TicketPriority | None = Field(default=None, description="Target priority tier")
    assigned_actor_id: str | None = Field(
        default=None, max_length=100, description="Target assignee identifier or None to unassign"
    )
    customer_id: uuid.UUID | None = Field(default=None, description="Target customer identifier")
    lock_version: int | None = Field(
        default=None, description="Expected lock version for optimistic concurrency control"
    )


class TicketResponse(BaseModel):
    """Public representation of a support ticket."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    ticket_number: int
    ticket_reference: str
    subject: str
    status: TicketStatus
    priority: TicketPriority
    channel: TicketChannel
    assigned_actor_id: str | None = None
    first_response_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    external_reference: str | None = None
    lock_version: int
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    """Paginated list of support tickets."""

    items: list[TicketResponse]
    total: int
    limit: int
    offset: int


class TicketEventResponse(BaseModel):
    """Historical audit event for a ticket mutation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    organization_id: uuid.UUID
    event_type: str
    event_timestamp: datetime
    actor_type: str
    actor_id: str | None = None
    previous_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None


class TicketEventListResponse(BaseModel):
    """List of historical lifecycle events for a ticket."""

    items: list[TicketEventResponse]
    total: int
    limit: int
    offset: int
