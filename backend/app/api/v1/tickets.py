"""FastAPI router for organization-scoped support tickets and ticket events."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrganizationContext, get_organization_context
from app.db.session import get_db_session
from app.models.enums import TicketChannel, TicketPriority, TicketStatus
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
)
from app.schemas.ticket import (
    TicketCreateRequest,
    TicketEventListResponse,
    TicketEventResponse,
    TicketListResponse,
    TicketResponse,
    TicketUpdateRequest,
)
from app.services.conversation_service import ConversationService
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/organizations/{organization_id}/tickets", tags=["Tickets"])


@router.post(
    "",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new support ticket",
    description="Provision a ticket with atomic sequence allocation, optional initial message, and audit event.",
)
async def create_ticket(
    payload: TicketCreateRequest,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TicketResponse:
    ticket = await TicketService.create_ticket(db, context, payload)
    return TicketResponse.model_validate(ticket)


@router.get(
    "",
    response_model=TicketListResponse,
    status_code=status.HTTP_200_OK,
    summary="List organization tickets",
    description="Retrieve paginated tickets filtered by status, priority, assignee, customer, channel, or search.",
)
async def list_tickets(
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    status: TicketStatus | None = Query(default=None, description="Filter by operational status"),
    priority: TicketPriority | None = Query(default=None, description="Filter by priority tier"),
    assigned_actor_id: str | None = Query(
        default=None, description="Filter by assigned user or actor ID"
    ),
    customer_id: uuid.UUID | None = Query(default=None, description="Filter by customer UUID"),
    channel: TicketChannel | None = Query(default=None, description="Filter by origin channel"),
    search: str | None = Query(
        default=None, max_length=100, description="Search keyword in ticket subject"
    ),
    sort_by: str = Query(
        default="created_at",
        description="Field to sort by (created_at, updated_at, priority, status)",
    ),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort order"),
    limit: int = Query(default=20, ge=1, le=100, description="Page limit (max 100)"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
) -> TicketListResponse:
    items, total = await TicketService.list_tickets(
        session=db,
        context=context,
        status=status,
        priority=priority,
        assigned_actor_id=assigned_actor_id,
        customer_id=customer_id,
        channel=channel,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return TicketListResponse(
        items=[TicketResponse.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ticket details",
    description="Retrieve a single ticket by UUID. Denies access with 404 if ticket belongs to another tenant.",
)
async def get_ticket(
    ticket_id: uuid.UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
) -> TicketResponse:
    ticket = await TicketService.get_ticket(context, ticket_id)
    return TicketResponse.model_validate(ticket)


@router.patch(
    "/{ticket_id}",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a support ticket",
    description="Apply partial mutations under optimistic concurrency control with domain transition validation.",
)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdateRequest,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TicketResponse:
    ticket = await TicketService.update_ticket(db, context, ticket_id, payload)
    return TicketResponse.model_validate(ticket)


@router.get(
    "/{ticket_id}/events",
    response_model=TicketEventListResponse,
    status_code=status.HTTP_200_OK,
    summary="List ticket lifecycle audit events",
    description="Read-only chronological audit log of all mutations that occurred on the ticket.",
)
async def list_ticket_events(
    ticket_id: uuid.UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=100, description="Max events to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> TicketEventListResponse:
    items, total = await TicketService.list_ticket_events(db, context, ticket_id, limit, offset)
    return TicketEventListResponse(
        items=[TicketEventResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{ticket_id}/conversations",
    response_model=ConversationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List conversations for a ticket",
    description="Retrieve all conversation threads attached to this ticket.",
)
async def list_ticket_conversations(
    ticket_id: uuid.UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConversationListResponse:
    items = await ConversationService.list_conversations_for_ticket(db, context, ticket_id)
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=len(items),
    )


@router.post(
    "/{ticket_id}/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an additional conversation thread",
    description="Create a new communication thread on an existing ticket.",
)
async def create_ticket_conversation(
    ticket_id: uuid.UUID,
    payload: ConversationCreateRequest,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ConversationResponse:
    conv = await ConversationService.create_conversation(db, context, ticket_id, payload)
    return ConversationResponse.model_validate(conv)
