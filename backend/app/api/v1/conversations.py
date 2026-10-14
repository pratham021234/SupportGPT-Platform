"""FastAPI router for organization-scoped conversations, messages, and attachments."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrganizationContext, get_organization_context
from app.db.session import get_db_session
from app.schemas.attachment import AttachmentListResponse, AttachmentResponse
from app.schemas.conversation import ConversationResponse
from app.schemas.message import (
    MessageCreateRequest,
    MessageListResponse,
    MessageResponse,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/organizations/{organization_id}/conversations", tags=["Conversations"])


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get conversation thread details",
    description="Retrieve conversation thread metadata strictly within active tenant.",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
) -> ConversationResponse:
    conv = await ConversationService.get_conversation(context, conversation_id)
    return ConversationResponse.model_validate(conv)


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    status_code=status.HTTP_200_OK,
    summary="List messages in a conversation",
    description="Retrieve paginated messages in deterministic chronological order.",
)
async def list_messages(
    conversation_id: uuid.UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=100, description="Max messages to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> MessageListResponse:
    items, total = await ConversationService.list_messages(db, context, conversation_id, limit, offset)
    return MessageListResponse(
        items=[MessageResponse.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post a message to a conversation thread",
    description="Append a communication record with author validation and external idempotency.",
)
async def create_message(
    conversation_id: uuid.UUID,
    payload: MessageCreateRequest,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    msg = await ConversationService.create_message(db, context, conversation_id, payload)
    return MessageResponse.model_validate(msg)


@router.get(
    "/{conversation_id}/messages/{message_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Get message details",
    description="Retrieve a single message within its verified parent conversation and tenant.",
)
async def get_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MessageResponse:
    msg = await ConversationService.get_message(db, context, conversation_id, message_id)
    return MessageResponse.model_validate(msg)


@router.get(
    "/{conversation_id}/messages/{message_id}/attachments",
    response_model=AttachmentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List attachment metadata for a message",
    description="Retrieve safe attachment metadata records without exposing internal storage locator keys.",
)
async def list_message_attachments(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AttachmentListResponse:
    items = await ConversationService.list_attachments_for_message(db, context, conversation_id, message_id)
    return AttachmentListResponse(
        items=[AttachmentResponse.model_validate(a) for a in items],
        total=len(items),
    )
