"""Pydantic schemas for webhook ingestion receipts, operational queries, and worker diagnostics."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WebhookReceptionResponse(BaseModel):
    """Immediate HTTP response upon receiving an inbound event."""

    receipt_id: uuid.UUID
    status: str
    duplicate: bool
    received_at: datetime


class IngestionReceiptResponse(BaseModel):
    """Metadata of an accepted event ingestion receipt."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    source_id: uuid.UUID | None
    source_provider: str
    external_event_id: str
    event_type: str
    status: str
    received_at: datetime
    processed_at: datetime | None
    attempt_count: int
    next_attempt_at: datetime | None
    error_code: str | None
    error_summary: str | None
    payload_digest: str | None
    correlation_id: str | None
    schema_version: str


class IngestionReceiptDetailResponse(IngestionReceiptResponse):
    """Detailed receipt record including sanitized payload for operators."""

    payload: dict[str, Any] | None = None


class IngestionReceiptListResponse(BaseModel):
    """Paginated collection of ingestion receipts."""

    items: list[IngestionReceiptResponse]
    total: int
    limit: int
    offset: int


class WorkerHealthResponse(BaseModel):
    """Diagnostic operational status of the background ingestion engine."""

    status: str = Field(..., description="Worker status: running, stopped, degraded")
    worker_id: str | None = Field(default=None)
    queue_depth: int = Field(..., description="Number of events queued or waiting for retry")
    processing_count: int = Field(..., description="Number of events currently leased by workers")
    dead_letter_count: int = Field(..., description="Number of events in dead_letter status")
    quarantined_count: int = Field(
        ..., description="Number of events quarantined for manual review"
    )
    lease_timeout_seconds: int = Field(...)
    active_workers: int = Field(default=1)


class ReplayRequest(BaseModel):
    """Operational payload to request re-queuing a failed or quarantined event."""

    force: bool = Field(
        default=False, description="Whether to bypass dead_letter requirement and reset attempts"
    )
