"""Inbound webhook reception endpoints for external provider events."""

import uuid

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException
from app.db.session import get_db_session
from app.schemas.ingestion import WebhookReceptionResponse
from app.services.ingestion_service import IngestionService

router = APIRouter(prefix="/webhooks", tags=["Webhooks & Event Ingestion"])


@router.post(
    "/sources/{source_id}",
    response_model=WebhookReceptionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive an authenticated inbound webhook for a configured source",
)
async def receive_source_webhook(
    request: Request,
    response: Response,
    source_id: uuid.UUID = Path(..., description="UUID of the configured event source"),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookReceptionResponse:
    """Accept and durably record an external webhook event for asynchronous processing.

    Enforces:
    - 1MB request size limit.
    - Content-Type: application/json.
    - Constant-time HMAC-SHA256 signature verification.
    - Timestamp clock-skew replay protection (5 minutes).
    - Database-level deduplication on (organization_id, provider, external_event_id).
    """
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    receipt, is_duplicate = await IngestionService.receive_webhook(
        session=db,
        source_id=source_id,
        raw_body=raw_body,
        headers=headers,
    )

    if is_duplicate:
        response.status_code = status.HTTP_200_OK

    return WebhookReceptionResponse(
        receipt_id=receipt.id,
        status=receipt.status,
        duplicate=is_duplicate,
        received_at=receipt.received_at,
    )


@router.post(
    "/generic",
    response_model=WebhookReceptionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive an inbound webhook with source ID supplied via header or query parameter",
)
async def receive_generic_webhook(
    request: Request,
    response: Response,
    x_source_id: uuid.UUID | None = Header(default=None, alias="X-SupportGPT-Source-ID"),
    source_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> WebhookReceptionResponse:
    """Accept generic webhook routing to source configuration via header or query parameter."""
    target_source_id = x_source_id or source_id
    if not target_source_id:
        raise ConflictException(
            "Source ID must be provided via 'X-SupportGPT-Source-ID' header or 'source_id' query parameter.",
            code="MISSING_SOURCE_ID",
        )

    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    receipt, is_duplicate = await IngestionService.receive_webhook(
        session=db,
        source_id=target_source_id,
        raw_body=raw_body,
        headers=headers,
    )

    if is_duplicate:
        response.status_code = status.HTTP_200_OK

    return WebhookReceptionResponse(
        receipt_id=receipt.id,
        status=receipt.status,
        duplicate=is_duplicate,
        received_at=receipt.received_at,
    )
