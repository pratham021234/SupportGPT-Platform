"""Tenant-scoped query abstraction and PostgreSQL Row-Level Security (RLS) context management."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.event_source import EventSource
from app.models.ingestion_receipt import IngestionReceipt
from app.models.knowledge_base import KnowledgeBase
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

    async def get_event_source(self, source_id: uuid.UUID) -> EventSource | None:
        """Retrieve an event source strictly scoped to the active organization."""
        query = select(EventSource).where(
            EventSource.id == source_id,
            EventSource.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_ingestion_receipt(self, receipt_id: uuid.UUID) -> IngestionReceipt | None:
        """Retrieve an ingestion receipt strictly scoped to the active organization."""
        query = select(IngestionReceipt).where(
            IngestionReceipt.id == receipt_id,
            IngestionReceipt.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_event_sources(self) -> Sequence[EventSource]:
        """List event sources strictly within the active organization."""
        query = (
            select(EventSource)
            .where(EventSource.organization_id == self.organization_id)
            .order_by(EventSource.created_at.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_ingestion_receipts(
        self, limit: int = 50, offset: int = 0
    ) -> Sequence[IngestionReceipt]:
        """List ingestion receipts strictly within the active organization."""
        query = (
            select(IngestionReceipt)
            .where(IngestionReceipt.organization_id == self.organization_id)
            .order_by(IngestionReceipt.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_knowledge_base(self, kb_id: uuid.UUID) -> KnowledgeBase | None:
        """Retrieve a knowledge base strictly scoped to the active organization."""
        query = select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_knowledge_bases(
        self, limit: int = 50, offset: int = 0
    ) -> Sequence[KnowledgeBase]:
        """List knowledge bases strictly within the active organization."""
        query = (
            select(KnowledgeBase)
            .where(KnowledgeBase.organization_id == self.organization_id)
            .order_by(KnowledgeBase.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_document(self, document_id: uuid.UUID) -> Document | None:
        """Retrieve a document strictly scoped to the active organization."""
        query = select(Document).where(
            Document.id == document_id,
            Document.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        kb_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
    ) -> Sequence[Document]:
        """List active documents strictly within the active organization."""
        from app.models.enums import DocumentLifecycleStatus

        query = select(Document).where(
            Document.organization_id == self.organization_id,
            Document.lifecycle_status != DocumentLifecycleStatus.DELETED,
        )
        if kb_id:
            query = query.where(Document.knowledge_base_id == kb_id)
        if not include_archived:
            query = query.where(Document.lifecycle_status == DocumentLifecycleStatus.ACTIVE)

        query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_document_version(
        self, document_id: uuid.UUID, version_id: uuid.UUID
    ) -> DocumentVersion | None:
        """Retrieve a specific document version strictly scoped to the active organization."""
        query = select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
            DocumentVersion.organization_id == self.organization_id,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_document_versions(self, document_id: uuid.UUID) -> Sequence[DocumentVersion]:
        """List all versions of a document strictly within the active organization."""
        query = (
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == self.organization_id,
            )
            .order_by(DocumentVersion.version_number.desc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_document_chunks(
        self, version_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> Sequence[DocumentChunk]:
        """List chunks for a specific document version strictly scoped to the active organization."""
        query = (
            select(DocumentChunk)
            .where(
                DocumentChunk.version_id == version_id,
                DocumentChunk.organization_id == self.organization_id,
            )
            .order_by(DocumentChunk.sequence_number.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
