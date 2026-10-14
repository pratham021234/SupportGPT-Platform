"""Tenant-scoped query abstraction and PostgreSQL Row-Level Security (RLS) context management."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.message import Message
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent


async def set_tenant_rls_context(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Set transaction-local PostgreSQL RLS context variable for tenant isolation.

    Uses `set_config(..., is_local=true)` so the variable automatically resets at transaction commit or rollback,
    preventing any context leakage across connection pool reuse.
    """
    await session.execute(
        text("SELECT set_config('app.current_organization_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )


class TenantScopedQuery:
    """Authoritative repository helper enforcing tenant isolation on all queries.

    Guarantees that database lookups are unconditionally filtered by the caller's
    authorized organization_id. Target records belonging to other tenants return None,
    preventing existence disclosure or unauthorized cross-tenant data access.
    """

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get_ticket(self, ticket_id: uuid.UUID) -> Ticket | None:
        """Retrieve a ticket strictly scoped to the active organization."""
        query = select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_customer(self, customer_id: uuid.UUID) -> Customer | None:
        """Retrieve a customer strictly scoped to the active organization."""
        query = select(Customer).where(
            Customer.id == customer_id,
            Customer.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_conversation(self, conversation_id: uuid.UUID) -> Conversation | None:
        """Retrieve a conversation strictly scoped to the active organization."""
        query = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_message(self, message_id: uuid.UUID) -> Message | None:
        """Retrieve a message strictly scoped to the active organization."""
        query = select(Message).where(
            Message.id == message_id,
            Message.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_attachment(self, attachment_id: uuid.UUID) -> Attachment | None:
        """Retrieve an attachment strictly scoped to the active organization."""
        query = select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_ticket_event(self, event_id: uuid.UUID) -> TicketEvent | None:
        """Retrieve a ticket lifecycle event strictly scoped to the active organization."""
        query = select(TicketEvent).where(
            TicketEvent.id == event_id,
            TicketEvent.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_tickets(self, limit: int = 50, offset: int = 0) -> Sequence[Ticket]:
        """List tickets strictly within the active organization."""
        query = (
            select(Ticket)
            .where(Ticket.organization_id == self.organization_id)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_customers(self, limit: int = 50, offset: int = 0) -> Sequence[Customer]:
        """List customers strictly within the active organization."""
        query = (
            select(Customer)
            .where(Customer.organization_id == self.organization_id)
            .order_by(Customer.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
