"""Organization-scoped external event sources administration endpoints."""

import uuid

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    OrganizationContext,
    require_permission,
)
from app.core.rbac import Permission
from app.db.session import get_db_session
from app.schemas.event_source import (
    SourceCreateRequest,
    SourceCreateResponse,
    SourceListResponse,
    SourceResponse,
    SourceUpdateRequest,
)
from app.services.ingestion_service import IngestionService

router = APIRouter(
    prefix="/organizations/{organization_id}/sources",
    tags=["Event Sources & Connectors"],
)


@router.post(
    "",
    response_model=SourceCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new external event source for the organization",
)
async def create_source(
    payload: SourceCreateRequest,
    context: OrganizationContext = Depends(require_permission(Permission.SOURCES_MANAGE)),
    db: AsyncSession = Depends(get_db_session),
) -> SourceCreateResponse:
    """Create a new external integration source.

    Returns the generated signing secret exactly once in `secret_value`.
    The secret is never stored in plain text or returned in subsequent queries.
    """
    source, secret_value = await IngestionService.create_source(
        session=db,
        organization_id=context.organization.id,
        payload=payload,
    )

    resp = SourceCreateResponse.model_validate(source)
    resp.secret_value = secret_value
    return resp


@router.get(
    "",
    response_model=SourceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all external sources configured for the organization",
)
async def list_sources(
    context: OrganizationContext = Depends(require_permission(Permission.SOURCES_READ)),
    db: AsyncSession = Depends(get_db_session),
) -> SourceListResponse:
    """Retrieve all external event sources configured in the active tenant organization."""
    sources = await IngestionService.list_sources(
        session=db,
        organization_id=context.organization.id,
    )
    items = [SourceResponse.model_validate(s) for s in sources]
    return SourceListResponse(items=items, total=len(items))


@router.get(
    "/{source_id}",
    response_model=SourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve external source configuration details",
)
async def get_source(
    source_id: uuid.UUID = Path(..., description="UUID of the event source"),
    context: OrganizationContext = Depends(require_permission(Permission.SOURCES_READ)),
    db: AsyncSession = Depends(get_db_session),
) -> SourceResponse:
    """Retrieve metadata and status of an event source with tenant isolation guarantee."""
    source = await IngestionService.get_source(
        session=db,
        organization_id=context.organization.id,
        source_id=source_id,
    )
    return SourceResponse.model_validate(source)


@router.patch(
    "/{source_id}",
    response_model=SourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing external event source",
)
async def update_source(
    payload: SourceUpdateRequest,
    source_id: uuid.UUID = Path(..., description="UUID of the event source"),
    context: OrganizationContext = Depends(require_permission(Permission.SOURCES_MANAGE)),
    db: AsyncSession = Depends(get_db_session),
) -> SourceResponse:
    """Update name, status, or supported event types of an event source."""
    source = await IngestionService.update_source(
        session=db,
        organization_id=context.organization.id,
        source_id=source_id,
        payload=payload,
    )
    return SourceResponse.model_validate(source)


@router.post(
    "/{source_id}/rotate-secret",
    response_model=SourceCreateResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate the signing secret for an external source",
)
async def rotate_secret(
    source_id: uuid.UUID = Path(..., description="UUID of the event source"),
    context: OrganizationContext = Depends(require_permission(Permission.SOURCES_MANAGE)),
    db: AsyncSession = Depends(get_db_session),
) -> SourceCreateResponse:
    """Rotate signing secret, immediately invalidating old credentials and returning new secret once."""
    source, new_secret = await IngestionService.rotate_secret(
        session=db,
        organization_id=context.organization.id,
        source_id=source_id,
    )
    resp = SourceCreateResponse.model_validate(source)
    resp.secret_value = new_secret
    return resp
