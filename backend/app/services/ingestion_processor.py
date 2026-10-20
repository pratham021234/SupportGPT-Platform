"""Idempotent domain mapping and transaction handling for normalized events."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, ResourceNotFoundException
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity, normalize_identity_value
from app.models.enums import (
    AuthorType,
    CustomerStatus,
    IdentityType,
    IdentityVerificationStatus,
    IngestionStatus,
    MessageDirection,
    SourceStatus,
    TicketChannel,
    TicketPriority,
    TicketStatus,
)
from app.models.event_source import EventSource
from app.models.ingestion_receipt import IngestionReceipt
from app.models.ticket import Ticket
from app.schemas.canonical_event import CanonicalCustomer, CanonicalEvent
from app.schemas.message import MessageCreateRequest
from app.schemas.ticket import TicketCreateRequest, TicketUpdateRequest
from app.services.conversation_service import ConversationService
from app.services.ticket_service import TicketService


class IngestionProcessor:
    """Processes normalized canonical events and applies domain mutations idempotently."""

    @staticmethod
    async def resolve_or_create_customer(
        session: AsyncSession,
        organization_id: uuid.UUID,
        customer_info: CanonicalCustomer | None,
    ) -> Customer | None:
        """Resolve an existing customer identity within the organization or provision a new record."""
        if not customer_info:
            return None

        # 1. Resolve by normalized Email
        if customer_info.email:
            norm_email = normalize_identity_value(IdentityType.EMAIL, customer_info.email)
            query = select(CustomerIdentity).where(
                CustomerIdentity.organization_id == organization_id,
                CustomerIdentity.identity_type == IdentityType.EMAIL,
                CustomerIdentity.normalized_value == norm_email,
            )
            result = await session.execute(query)
            identity = result.scalar_one_or_none()
            if identity:
                cust = await session.get(Customer, identity.customer_id)
                if cust:
                    return cust

            # Provision new customer with email identity
            display_name = customer_info.name or norm_email.split("@")[0]
            new_customer = Customer(
                organization_id=organization_id,
                display_name=display_name,
                status=CustomerStatus.ACTIVE,
            )
            session.add(new_customer)
            await session.flush()

            new_identity = CustomerIdentity(
                organization_id=organization_id,
                customer_id=new_customer.id,
                identity_type=IdentityType.EMAIL,
                normalized_value=norm_email,
                raw_value=customer_info.email,
                verification_status=IdentityVerificationStatus.VERIFIED,
            )
            session.add(new_identity)
            await session.flush()
            return new_customer

        # 2. Resolve by External Account/Provider ID
        if customer_info.external_id:
            norm_ext_id = normalize_identity_value(
                IdentityType.PROVIDER_SPECIFIC, customer_info.external_id
            )
            query = select(CustomerIdentity).where(
                CustomerIdentity.organization_id == organization_id,
                CustomerIdentity.identity_type == IdentityType.PROVIDER_SPECIFIC,
                CustomerIdentity.normalized_value == norm_ext_id,
            )
            result = await session.execute(query)
            identity = result.scalar_one_or_none()
            if identity:
                cust = await session.get(Customer, identity.customer_id)
                if cust:
                    return cust

            display_name = customer_info.name or f"User-{customer_info.external_id[:8]}"
            new_customer = Customer(
                organization_id=organization_id,
                display_name=display_name,
                status=CustomerStatus.ACTIVE,
            )
            session.add(new_customer)
            await session.flush()

            new_identity = CustomerIdentity(
                organization_id=organization_id,
                customer_id=new_customer.id,
                identity_type=IdentityType.PROVIDER_SPECIFIC,
                normalized_value=norm_ext_id,
                raw_value=customer_info.external_id,
                verification_status=IdentityVerificationStatus.VERIFIED,
            )
            session.add(new_identity)
            await session.flush()
            return new_customer

        return None

    @classmethod
    async def process_event(
        cls,
        session: AsyncSession,
        event: CanonicalEvent,
        receipt: IngestionReceipt,
    ) -> dict[str, Any]:
        """Apply domain mutations corresponding to the canonical event.

        Guarantees idempotency: retried executions will not create duplicate tickets or messages.
        """
        org_id = receipt.organization_id

        # 1. Validate Source Status
        if receipt.source_id:
            src_res = await session.execute(
                select(EventSource).where(
                    EventSource.id == receipt.source_id,
                    EventSource.organization_id == org_id,
                )
            )
            source = src_res.scalar_one_or_none()
            if not source or source.status != SourceStatus.ACTIVE:
                receipt.status = IngestionStatus.FAILED
                receipt.error_code = "SOURCE_INACTIVE"
                receipt.error_summary = (
                    f"Event source '{receipt.source_id}' is inactive or deleted."
                )
                return {"status": "failed", "error": receipt.error_summary}

            source.last_event_at = datetime.now(UTC)

        # 2. Customer Resolution
        customer = await cls.resolve_or_create_customer(session, org_id, event.customer)

        # 3. Route according to event_type
        if event.event_type in ("ticket.created", "inbound_ticket"):
            return await cls._handle_ticket_created(session, org_id, event, customer)

        elif event.event_type in ("message.received", "inbound_message"):
            return await cls._handle_message_received(session, org_id, event, customer)

        elif event.event_type in ("ticket.updated", "status_change"):
            return await cls._handle_ticket_updated(session, org_id, event)

        else:
            # Generic event type recorded safely without domain mutation
            return {
                "action": "ignored_or_recorded",
                "event_type": event.event_type,
                "message": "Event recognized but requires no domain mutation.",
            }

    @classmethod
    async def _handle_ticket_created(
        cls,
        session: AsyncSession,
        org_id: uuid.UUID,
        event: CanonicalEvent,
        customer: Customer | None,
    ) -> dict[str, Any]:
        """Handle ticket.created event with idempotency check against external_ticket_id."""
        # Check if ticket already exists by external_reference
        if event.external_ticket_id:
            query = select(Ticket).where(
                Ticket.organization_id == org_id,
                Ticket.external_reference == event.external_ticket_id,
            )
            res = await session.execute(query)
            existing_ticket = res.scalar_one_or_none()
            if existing_ticket:
                return {
                    "action": "existing_ticket_reused",
                    "ticket_id": str(existing_ticket.id),
                    "ticket_number": existing_ticket.ticket_number,
                }

        create_payload = TicketCreateRequest(
            subject=event.subject or f"Inbound event from {event.provider}",
            description=event.message_body,
            priority=event.priority or TicketPriority.MEDIUM,
            channel=TicketChannel.API,
            customer_id=customer.id if customer else None,
            external_reference=event.external_ticket_id,
        )

        ticket = await TicketService.create_ticket_internal(
            session=session,
            organization_id=org_id,
            payload=create_payload,
            actor_id=None,
            actor_type=AuthorType.SYSTEM,
            direction=MessageDirection.INBOUND,
            auto_commit=False,
        )

        return {
            "action": "ticket_created",
            "ticket_id": str(ticket.id),
            "ticket_number": ticket.ticket_number,
        }

    @classmethod
    async def _handle_message_received(
        cls,
        session: AsyncSession,
        org_id: uuid.UUID,
        event: CanonicalEvent,
        customer: Customer | None,
    ) -> dict[str, Any]:
        """Append inbound message to target ticket's conversation with idempotency on external_message_id."""
        # 1. Resolve Target Ticket
        ticket = None
        if event.external_ticket_id:
            query = select(Ticket).where(
                Ticket.organization_id == org_id,
                Ticket.external_reference == event.external_ticket_id,
            )
            res = await session.execute(query)
            ticket = res.scalar_one_or_none()

        if not ticket:
            # If ticket does not exist yet, provision one so message is never dropped
            create_payload = TicketCreateRequest(
                subject=event.subject or f"Inbound conversation from {event.provider}",
                description=None,
                priority=event.priority or TicketPriority.MEDIUM,
                channel=TicketChannel.API,
                customer_id=customer.id if customer else None,
                external_reference=event.external_ticket_id,
            )
            ticket = await TicketService.create_ticket_internal(
                session=session,
                organization_id=org_id,
                payload=create_payload,
                actor_id=None,
                actor_type=AuthorType.SYSTEM,
                direction=MessageDirection.INBOUND,
                auto_commit=False,
            )

        # 2. Resolve Active Conversation
        conv_query = (
            select(Conversation)
            .where(
                Conversation.organization_id == org_id,
                Conversation.ticket_id == ticket.id,
            )
            .order_by(Conversation.created_at.asc())
        )
        conv_res = await session.execute(conv_query)
        conv = conv_res.scalars().first()
        if not conv:
            conv = await ConversationService.create_conversation_internal(
                session=session,
                organization_id=org_id,
                ticket_id=ticket.id,
                channel_type=ticket.channel,
                auto_commit=False,
            )

        # 3. Append Message Idempotently
        body_content = (
            event.message_body.strip()
            if event.message_body and event.message_body.strip()
            else "[No text content]"
        )
        msg_payload = MessageCreateRequest(
            body_text=body_content,
            author_type=AuthorType.CUSTOMER,
            direction=MessageDirection.INBOUND,
            external_message_id=event.external_message_id,
        )

        try:
            message = await ConversationService.create_message_internal(
                session=session,
                organization_id=org_id,
                conversation_id=conv.id,
                payload=msg_payload,
                author_id=str(customer.id) if customer else None,
                sender_display_name=customer.display_name
                if customer
                else (event.customer.name if event.customer else None),
                auto_commit=False,
            )
            return {
                "action": "message_appended",
                "ticket_id": str(ticket.id),
                "conversation_id": str(conv.id),
                "message_id": str(message.id),
            }
        except ConflictException:
            # Duplicate message delivery with same external_message_id safely ignored
            return {
                "action": "duplicate_message_ignored",
                "ticket_id": str(ticket.id),
                "conversation_id": str(conv.id),
            }

    @classmethod
    async def _handle_ticket_updated(
        cls,
        session: AsyncSession,
        org_id: uuid.UUID,
        event: CanonicalEvent,
    ) -> dict[str, Any]:
        """Update ticket status or priority from inbound provider webhook."""
        if not event.external_ticket_id:
            raise ResourceNotFoundException("Ticket", "missing external_ticket_id")

        query = select(Ticket).where(
            Ticket.organization_id == org_id,
            Ticket.external_reference == event.external_ticket_id,
        )
        res = await session.execute(query)
        ticket = res.scalar_one_or_none()
        if not ticket:
            return {
                "action": "ticket_not_found_skipped",
                "external_reference": event.external_ticket_id,
            }

        status_val = None
        if event.metadata.get("status"):
            try:
                status_val = TicketStatus(str(event.metadata["status"]).lower())
            except ValueError:
                pass

        update_payload = TicketUpdateRequest(
            status=status_val,
            priority=event.priority,
            lock_version=ticket.lock_version,
        )
        updated_ticket = await TicketService.update_ticket_internal(
            session=session,
            organization_id=org_id,
            ticket_id=ticket.id,
            payload=update_payload,
            actor_id=None,
            actor_type=AuthorType.SYSTEM,
            auto_commit=False,
        )
        return {
            "action": "ticket_updated",
            "ticket_id": str(updated_ticket.id),
            "status": updated_ticket.status,
        }
