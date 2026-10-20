"""Domain business logic for conversation threads, messages, idempotency, and attachments."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrganizationContext
from app.core.errors import (
    ForbiddenException,
    ResourceNotFoundException,
)
from app.core.logging import get_logger
from app.core.rbac import Permission
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.enums import (
    AuthorType,
    ConversationStatus,
    MembershipRole,
    MessageDirection,
    TicketChannel,
)
from app.models.message import Message
from app.models.ticket import Ticket
from app.schemas.conversation import ConversationCreateRequest
from app.schemas.message import MessageCreateRequest

logger = get_logger("supportgpt.conversations")


class ConversationService:
    """Service managing communication threads, message sequences, and attachment metadata."""

    @staticmethod
    async def list_conversations_for_ticket(
        session: AsyncSession,
        context: OrganizationContext,
        ticket_id: uuid.UUID,
    ) -> list[Conversation]:
        """List all conversation threads associated with a ticket in the organization."""
        if not context.has_permission(Permission.TICKETS_READ):
            raise ForbiddenException("Permission 'tickets:read' required to view conversations.")

        org_id = context.organization.id
        ticket = await context.tenant_query.get_ticket(ticket_id)
        if not ticket:
            raise ResourceNotFoundException("Ticket", ticket_id)

        query = (
            select(Conversation)
            .where(
                Conversation.organization_id == org_id,
                Conversation.ticket_id == ticket_id,
            )
            .order_by(Conversation.created_at.asc(), Conversation.id.asc())
        )
        res = await session.execute(query)
        return list(res.scalars().all())

    @staticmethod
    async def create_conversation_internal(
        session: AsyncSession,
        organization_id: uuid.UUID,
        ticket_id: uuid.UUID,
        channel_type: TicketChannel = TicketChannel.API,
        external_thread_id: str | None = None,
        auto_commit: bool = True,
    ) -> Conversation:
        """Internal conversation creation for background workflows and integrations."""
        conversation = Conversation(
            organization_id=organization_id,
            ticket_id=ticket_id,
            channel_type=channel_type,
            external_thread_id=external_thread_id,
            status=ConversationStatus.ACTIVE,
        )
        session.add(conversation)
        if auto_commit:
            await session.commit()
            await session.refresh(conversation)
        else:
            await session.flush()
        return conversation

    @staticmethod
    async def create_conversation(
        session: AsyncSession,
        context: OrganizationContext,
        ticket_id: uuid.UUID,
        payload: ConversationCreateRequest,
    ) -> Conversation:
        """Create a new conversation thread on a ticket."""
        if not context.has_permission(Permission.TICKETS_WRITE):
            raise ForbiddenException("Permission 'tickets:write' required to create conversations.")

        org_id = context.organization.id
        ticket = await context.tenant_query.get_ticket(ticket_id)
        if not ticket:
            raise ResourceNotFoundException("Ticket", ticket_id)

        return await ConversationService.create_conversation_internal(
            session=session,
            organization_id=org_id,
            ticket_id=ticket.id,
            channel_type=payload.channel_type,
            external_thread_id=payload.external_thread_id,
            auto_commit=True,
        )

    @staticmethod
    async def get_conversation(
        context: OrganizationContext,
        conversation_id: uuid.UUID,
    ) -> Conversation:
        """Retrieve conversation by ID strictly within the active tenant."""
        if not context.has_permission(Permission.TICKETS_READ):
            raise ForbiddenException("Permission 'tickets:read' required to view conversation.")

        conversation = await context.tenant_query.get_conversation(conversation_id)
        if not conversation:
            raise ResourceNotFoundException("Conversation", conversation_id)
        return conversation

    @staticmethod
    async def list_messages(
        session: AsyncSession,
        context: OrganizationContext,
        conversation_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        """List messages in a conversation in deterministic chronological sequence."""
        if not context.has_permission(Permission.TICKETS_READ):
            raise ForbiddenException("Permission 'tickets:read' required to view messages.")

        org_id = context.organization.id
        conv = await context.tenant_query.get_conversation(conversation_id)
        if not conv:
            raise ResourceNotFoundException("Conversation", conversation_id)

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        count_stmt = select(func.count(Message.id)).where(
            Message.organization_id == org_id,
            Message.conversation_id == conversation_id,
        )
        total = (await session.execute(count_stmt)).scalar_one()

        query = (
            select(Message)
            .where(
                Message.organization_id == org_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc(), Message.sequence_number.asc(), Message.id.asc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(query)
        items = list(res.scalars().all())
        return items, total

    @staticmethod
    async def create_message_internal(
        session: AsyncSession,
        organization_id: uuid.UUID,
        conversation_id: uuid.UUID,
        payload: MessageCreateRequest,
        author_id: str | None = None,
        sender_display_name: str | None = None,
        auto_commit: bool = True,
    ) -> Message:
        """Internal message creation for background workers and inbound webhooks."""
        conv_stmt = select(Conversation).where(
            Conversation.organization_id == organization_id,
            Conversation.id == conversation_id,
        )
        conv_res = await session.execute(conv_stmt)
        conv = conv_res.scalar_one_or_none()
        if not conv:
            raise ResourceNotFoundException("Conversation", conversation_id)

        # 1. Idempotency check on external_message_id
        if payload.external_message_id and payload.external_message_id.strip():
            existing_query = select(Message).where(
                Message.organization_id == organization_id,
                Message.external_message_id == payload.external_message_id.strip(),
            )
            existing_res = await session.execute(existing_query)
            existing_msg = existing_res.scalar_one_or_none()
            if existing_msg:
                logger.info(
                    f"Idempotent message hit for external_id: {payload.external_message_id}"
                )
                return existing_msg

        # 2. Deterministic sequence number calculation
        seq_stmt = select(func.coalesce(func.max(Message.sequence_number), 0)).where(
            Message.conversation_id == conversation_id
        )
        current_max_seq = (await session.execute(seq_stmt)).scalar_one()
        next_seq = current_max_seq + 1

        message = Message(
            organization_id=organization_id,
            conversation_id=conversation_id,
            direction=payload.direction,
            author_type=payload.author_type,
            author_id=author_id,
            sender_display_name=sender_display_name,
            body_text=payload.body_text.strip(),
            body_rich=payload.body_rich,
            content_type=payload.content_type,
            external_message_id=payload.external_message_id.strip()
            if payload.external_message_id
            else None,
            sequence_number=next_seq,
            delivery_status="stored"
            if payload.direction == MessageDirection.OUTBOUND
            else "received",
        )
        session.add(message)

        # 3. Update parent conversation last_message_at
        conv.last_message_at = datetime.now(UTC)

        # 4. Update ticket first_response_at if this is the first outbound agent response
        if (
            payload.direction == MessageDirection.OUTBOUND
            and payload.author_type == AuthorType.AGENT
        ):
            tick_stmt = select(Ticket).where(
                Ticket.organization_id == organization_id,
                Ticket.id == conv.ticket_id,
            )
            tick_res = await session.execute(tick_stmt)
            ticket = tick_res.scalar_one_or_none()
            if ticket and ticket.first_response_at is None:
                ticket.first_response_at = datetime.now(UTC)

        if auto_commit:
            await session.commit()
            await session.refresh(message)
        else:
            await session.flush()

        logger.info(
            f"Created message {message.id} in conversation {conversation_id} (seq {next_seq})"
        )
        return message

    @staticmethod
    async def create_message(
        session: AsyncSession,
        context: OrganizationContext,
        conversation_id: uuid.UUID,
        payload: MessageCreateRequest,
    ) -> Message:
        """Post a message to an active conversation with idempotency and author validation."""
        if not context.has_permission(Permission.TICKETS_WRITE):
            raise ForbiddenException("Permission 'tickets:write' required to post messages.")

        org_id = context.organization.id

        # 1. Author role validation
        if payload.author_type in (AuthorType.SYSTEM, AuthorType.AI):
            if context.role not in (MembershipRole.OWNER, MembershipRole.ADMIN):
                raise ForbiddenException(
                    "Cannot submit message as system or AI without administrative authority."
                )

        author_id = str(context.user.id) if payload.author_type == AuthorType.AGENT else None
        sender_name = context.user.display_name if payload.author_type == AuthorType.AGENT else None

        return await ConversationService.create_message_internal(
            session=session,
            organization_id=org_id,
            conversation_id=conversation_id,
            payload=payload,
            author_id=author_id,
            sender_display_name=sender_name,
            auto_commit=True,
        )

    @staticmethod
    async def get_message(
        session: AsyncSession,
        context: OrganizationContext,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> Message:
        """Retrieve message ensuring parent conversation and organization integrity."""
        if not context.has_permission(Permission.TICKETS_READ):
            raise ForbiddenException("Permission 'tickets:read' required to view message.")

        conv = await context.tenant_query.get_conversation(conversation_id)
        if not conv:
            raise ResourceNotFoundException("Conversation", conversation_id)

        msg = await context.tenant_query.get_message(message_id)
        if not msg or msg.conversation_id != conversation_id:
            raise ResourceNotFoundException("Message", message_id)

        return msg

    @staticmethod
    async def list_attachments_for_message(
        session: AsyncSession,
        context: OrganizationContext,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> list[Attachment]:
        """Retrieve attachment metadata records associated with an accessible message."""
        if not context.has_permission(Permission.TICKETS_READ):
            raise ForbiddenException("Permission 'tickets:read' required to view attachments.")

        org_id = context.organization.id
        conv = await context.tenant_query.get_conversation(conversation_id)
        if not conv:
            raise ResourceNotFoundException("Conversation", conversation_id)

        msg = await context.tenant_query.get_message(message_id)
        if not msg or msg.conversation_id != conversation_id:
            raise ResourceNotFoundException("Message", message_id)

        query = (
            select(Attachment)
            .where(
                Attachment.organization_id == org_id,
                Attachment.message_id == message_id,
            )
            .order_by(Attachment.created_at.asc(), Attachment.id.asc())
        )
        res = await session.execute(query)
        return list(res.scalars().all())
