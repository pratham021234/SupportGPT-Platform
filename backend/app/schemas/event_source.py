"""Pydantic schemas for external source configuration and lifecycle management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SourceProvider, SourceStatus


class SourceCreateRequest(BaseModel):
    """Payload to register a new external event source."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ..., min_length=1, max_length=100, description="Human-readable label for the integration"
    )
    provider: SourceProvider = Field(
        default=SourceProvider.GENERIC_WEBHOOK,
        description="External provider or protocol type",
    )
    external_account_id: str | None = Field(
        default=None,
        max_length=255,
        description="Optional external account, workspace, or installation ID",
    )
    secret_reference: str | None = Field(
        default=None,
        max_length=255,
        description="Optional managed secret reference (e.g. env:NAME or vault:path)",
    )
    supported_event_types: list[str] = Field(
        default=["ticket.created", "ticket.updated", "message.received"],
        description="List of external event types this source is authorized to send",
    )


class SourceUpdateRequest(BaseModel):
    """Payload to update an existing external event source."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: SourceStatus | None = Field(default=None)
    external_account_id: str | None = Field(default=None, max_length=255)
    secret_reference: str | None = Field(default=None, max_length=255)
    supported_event_types: list[str] | None = Field(default=None)


class SourceResponse(BaseModel):
    """Public representation of an external event source configuration."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    provider: str
    name: str
    status: str
    external_account_id: str | None
    signing_secret_preview: str | None
    secret_reference: str | None
    supported_event_types: list[str]
    last_event_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SourceCreateResponse(SourceResponse):
    """Creation/Rotation response returning the generated signing secret exactly once."""

    secret_value: str | None = Field(
        default=None,
        description="Plain-text signing secret returned once upon creation or rotation. Never logged or stored in plain text.",
    )


class SourceListResponse(BaseModel):
    """Paginated collection of configured external sources."""

    items: list[SourceResponse]
    total: int
