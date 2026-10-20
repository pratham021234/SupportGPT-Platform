"""Operational ingestion receipt inspection, retry/replay APIs, and worker diagnostics."""

import uuid

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    OrganizationContext,
    require_permission,
)
from app.core.rbac import Permission
from app.db.session import get_db_session
from app.models.enums import IngestionStatus
from app.schemas.ingestion import (
    IngestionReceiptDetailResponse,
    IngestionReceiptListResponse,
    IngestionReceiptResponse,
    ReplayRequest,
    WorkerHealthResponse,
)
from app.services.ingestion_service import IngestionService
from app.services.ingestion_worker import IngestionWorker

# Organization-scoped operational receipts router
router = APIRouter(
    prefix="/organizations/{organization_id}/ingestion",
    tags=["Ingestion Operations & Receipts"],
)

# Diagnostics router for worker health
diagnostics_router = APIRouter(
    prefix="/ingestion",
    tags=["Ingestion Diagnostics"],
)


@router.get(
    "/receipts",
    response_model=IngestionReceiptListResponse,
    status_code=status.HTTP_200_OK,
    summary="List ingestion receipts within the organization",
)
async def list_receipts(
    status_filter: IngestionStatus | None = Query(default=None, alias="status"),
    provider: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: OrganizationContext = Depends(require_permission(Permission.INGESTION_READ)),
    db: AsyncSession = Depends(get_db_session),
) -> IngestionReceiptListResponse:
    """List and inspect inbound event receipts with tenant isolation enforcement."""
    items, total = await IngestionService.list_receipts(
        session=db,
        organization_id=context.organization.id,
        status=status_filter,
        provider=provider,
        limit=limit,
        offset=offset,
    )
    receipt_items = [IngestionReceiptResponse.model_validate(r) for r in items]
    return IngestionReceiptListResponse(
        items=receipt_items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/receipts/{receipt_id}",
    response_model=IngestionReceiptDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve ingestion receipt details including sanitized payload",
)
async def get_receipt(
    receipt_id: uuid.UUID = Path(..., description="UUID of the ingestion receipt"),
    context: OrganizationContext = Depends(require_permission(Permission.INGESTION_READ)),
    db: AsyncSession = Depends(get_db_session),
) -> IngestionReceiptDetailResponse:
    """Retrieve detailed metadata and payload of an ingestion receipt."""
    receipt = await IngestionService.get_receipt(
        session=db,
        organization_id=context.organization.id,
        receipt_id=receipt_id,
    )
    return IngestionReceiptDetailResponse.model_validate(receipt)


@router.post(
    "/receipts/{receipt_id}/replay",
    response_model=IngestionReceiptResponse,
    status_code=status.HTTP_200_OK,
    summary="Replay a failed or dead-lettered ingestion event",
)
async def replay_receipt(
    payload: ReplayRequest = ReplayRequest(),
    receipt_id: uuid.UUID = Path(..., description="UUID of the ingestion receipt"),
    context: OrganizationContext = Depends(require_permission(Permission.INGESTION_MANAGE)),
    db: AsyncSession = Depends(get_db_session),
) -> IngestionReceiptResponse:
    """Reset a dead-lettered or failed event to QUEUED status for background reprocessing.

    Maintains the original event identity, avoiding artificial duplicate creation.
    """
    receipt = await IngestionService.replay_receipt(
        session=db,
        organization_id=context.organization.id,
        receipt_id=receipt_id,
        force=payload.force,
    )
    return IngestionReceiptResponse.model_validate(receipt)


@diagnostics_router.get(
    "/worker/health",
    response_model=WorkerHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve ingestion background worker health, queue depth, and dead-letter statistics",
)
async def get_worker_health(
    db: AsyncSession = Depends(get_db_session),
) -> WorkerHealthResponse:
    """Operational diagnostics probe for background worker status and queue metrics."""
    return await IngestionWorker.get_health_metrics(db)
