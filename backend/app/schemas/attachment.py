"""Pydantic schemas for attachment metadata retrieval."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AttachmentScanStatus


class AttachmentResponse(BaseModel):
    """Sanitized attachment metadata representation without exposing raw object storage keys."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    message_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    checksum_sha256: str | None = None
    scan_status: AttachmentScanStatus
    created_at: datetime


class AttachmentListResponse(BaseModel):
    """List of attachment metadata records."""

    items: list[AttachmentResponse]
    total: int
