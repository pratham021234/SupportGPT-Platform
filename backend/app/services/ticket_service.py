"""Domain business logic for support ticket lifecycle, assignment, OCC, and history."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrganizationContext
from app.core.errors import (
    ConflictException,
    ForbiddenException,
    ResourceNotFoundException,
)
from app.core.logging import correlation_id_ctx, get_logger
from app.core.rbac import Permission
from app.db.tenant import set_tenant_rls_context
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import (
    AuthorType,
    ConversationStatus,
    MembershipRole,
    MembershipStatus,
    MessageDirection,
    TicketChannel,
    TicketEventType,
    TicketPriority,
    TicketStatus,
    can_transition_ticket_status,
)
from app.models.membership import OrganizationMembership
from app.models.message import Message
from app.models.organization import allocate_next_ticket_number
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.schemas.ticket import TicketCreateRequest, TicketUpdateRequest

logger = get_logger("supportgpt.tickets")


class TicketService:
    """Service orchestrating transactional ticket management and lifecycle event tracking."""

    @staticmethod
    async def validate_assignee(
        session: AsyncSession,
        organization_id: uuid.UUID,
        assignee_id_str: str | None,
    ) -> None:
        """Validate that target assignee belongs to organization, is active, and is eligible (not viewer)."""
        if not assignee_id_str:
            return

        try:
            user_uuid = uuid.UUID(assignee_id_str)
        except ValueError:
            # If actor is not a UUID (e.g. system bot), reject unless explicitly handled
            raise ConflictException(
                f"Assigned actor '{assignee_id_str}' is not a valid user identifier.",
                code="INVALID_ASSIGNEE",
            ) from None

        query = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_uuid,
        )
        res = await session.execute(query)
        membership = res.scalar_one_or_none()

        if not membership or membership.status != MembershipStatus.ACTIVE:
            raise ConflictException(
                f"User '{assignee_id_str}' does not hold an active membership in this organization.",
                code="INVALID_ASSIGNEE",
            )

        if membership.role == MembershipRole.VIEWER:
            raise ConflictException(
                f"Member '{assignee_id_str}' holds a read-only viewer role and cannot be assigned tickets.",
                code="INVALID_ASSIGNEE",
            )

    @staticmethod
    async def create_ticket_internal(
        session: AsyncSession,
        organization_id: uuid.UUID,
        payload: TicketCreateRequest,
        actor_id: str | None = None,
        actor_type: AuthorType = AuthorType.SYSTEM,
        author_display_name: str | None = None,
        direction: MessageDirection = MessageDirection.INBOUND,
        auto_commit: bool = True,
    ) -> Ticket:
        """Internal ticket creation logic accessible to background workers and internal workflows."""
        # 1. Validate customer if specified
        if payload.customer_id is not None:
            cust_stmt = select(Customer).where(
                Customer.organization_id == organization_id,
                Customer.id == payload.customer_id,
            )
            cust_res = await session.execute(cust_stmt)
            if not cust_res.scalar_one_or_none():
                raise ResourceNotFoundException("Customer", payload.customer_id)

        # 2. Concurrency-safe sequential ticket number allocation
        ticket_number = await allocate_next_ticket_number(session, organization_id)
        ticket_ref = f"TICK-{ticket_number}"

        ticket = Ticket(
            organization_id=organization_id,
            customer_id=payload.customer_id,
            ticket_number=ticket_number,
            ticket_reference=ticket_ref,
            subject=payload.subject.strip(),
            status=TicketStatus.OPEN,
            priority=payload.priority,
            channel=payload.channel,
            assigned_actor_id=payload.assigned_actor_id,
            external_reference=payload.external_reference,
            lock_version=1,
        )
        session.add(ticket)
        await session.flush()

        # 3. Create initial conversation and message if description provided
        if payload.description and payload.description.strip():
            conversation = Conversation(
                organization_id=organization_id,
                ticket_id=ticket.id,
                channel_type=ticket.channel,
                status=ConversationStatus.ACTIVE,
                last_message_at=datetime.now(UTC),
            )
            session.add(conversation)
            await session.flush()

            message = Message(
                organization_id=organization_id,
                conversation_id=conversation.id,
                direction=direction,
                author_type=actor_type,
                author_id=actor_id,
                sender_display_name=author_display_name,
                body_text=payload.description.strip(),
                content_type="text/plain",
                sequence_number=1,
                delivery_status="stored" if direction == MessageDirection.OUTBOUND else "received",
            )
            session.add(message)

        # 4. Create lifecycle event
        event = TicketEvent(
            organization_id=organization_id,
            ticket_id=ticket.id,
            event_type=TicketEventType.CREATED,
            event_timestamp=datetime.now(UTC),
            actor_type=actor_type,
            actor_id=actor_id or "system",
            new_value={
                "ticket_reference": ticket.ticket_reference,
                "subject": ticket.subject,
                "status": ticket.status,
                "priority": ticket.priority,
                "channel": ticket.channel,
                "assigned_actor_id": ticket.assigned_actor_id,
                "customer_id": str(ticket.customer_id) if ticket.customer_id else None,
            },
            payload={"source": "api" if actor_type == AuthorType.AGENT else "internal"},
            correlation_id=correlation_id_ctx.get(),
        )
        session.add(event)

        if auto_commit:
            await session.commit()
            try:
                await set_tenant_rls_context(session, organization_id)
            except Exception:
                pass
            await session.refresh(ticket)
        else:
            await session.flush()

        logger.info(
            f"Created ticket {ticket.ticket_reference} ({ticket.id}) in org {organization_id}"
        )
        return ticket

    @staticmethod
    async def create_ticket(
        session: AsyncSession,
        context: OrganizationContext,
        payload: TicketCreateRequest,
    ) -> Ticket:
        """Create a new ticket and optionally its initial conversation, message, and creation event."""
        if not context.has_permission(Permission.TICKETS_WRITE):
            raise ForbiddenException("Permission 'tickets:write' required to create tickets.")

        org_id = context.organization.id

        # 1. Validate assignee if specified
        if payload.assigned_actor_id is not None:
            if not context.has_permission(Permission.TICKETS_ASSIGN):
                raise ForbiddenException("Permission 'tickets:assign' required to assign tickets.")
            await TicketService.validate_assignee(session, org_id, payload.assigned_actor_id)

        return await TicketService.create_ticket_internal(
            session=session,
            organization_id=org_id,
            payload=payload,
            actor_id=str(context.user.id),
            actor_type=AuthorType.AGENT,
            author_display_name=context.user.display_name,
            direction=MessageDirection.OUTBOUND,
            auto_commit=True,
        )

    @staticmethod
    async def get_ticket(
        context: OrganizationContext,
        ticket_id: uuid.UUID,
    ) -> Ticket:
        """Retrieve a single ticket scoped to the active organization."""
        if not context.has_permission(Permission.TICKETS_READ):
            raise ForbiddenException("Permission 'tickets:read' required to view tickets.")

        ticket = await context.tenant_query.get_ticket(ticket_id)
        if not ticket:
            raise ResourceNotFoundException("Ticket", ticket_id)
        return ticket

    @staticmethod
    async def list_tickets(
        session: AsyncSession,
        context: OrganizationContext,
        status: TicketStatus | None = None,
        priority: TicketPriority | None = None,
        assigned_actor_id: str | None = None,
        customer_id: uuid.UUID | None = None,
        channel: TicketChannel | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Ticket], int]:
        """List tickets strictly within the active organization with filters, search, and pagination."""
        if not context.has_permission(Permission.TICKETS_READ):
            raise ForbiddenException("Permission 'tickets:read' required to list tickets.")

        org_id = context.organization.id
        limit = max(1, min(limit, 100))  # Bounded pagination
        offset = max(0, offset)

        conditions = [Ticket.organization_id == org_id]

        if status:
            conditions.append(Ticket.status == status)
        if priority:
            conditions.append(Ticket.priority == priority)
        if assigned_actor_id:
            conditions.append(Ticket.assigned_actor_id == assigned_actor_id)
        if customer_id:
            conditions.append(Ticket.customer_id == customer_id)
        if channel:
            conditions.append(Ticket.channel == channel)
        if search and search.strip():
            search_term = f"%{search.strip()}%"
            conditions.append(Ticket.subject.ilike(search_term))

        # Count total matches
        count_stmt = select(func.count(Ticket.id)).where(*conditions)
        count_res = await session.execute(count_stmt)
        total = count_res.scalar_one()

        # Sorting
        sort_column_map = {
            "created_at": Ticket.created_at,
            "updated_at": Ticket.updated_at,
            "priority": Ticket.priority,
            "status": Ticket.status,
            "ticket_number": Ticket.ticket_number,
        }
        sort_col = sort_column_map.get(sort_by, Ticket.created_at)
        order_clause = sort_col.asc() if sort_order.lower() == "asc" else sort_col.desc()

        # Deterministic secondary sort key
        query = (
            select(Ticket)
            .where(*conditions)
            .order_by(order_clause, Ticket.id.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(query)
        items = list(res.scalars().all())

        return items, total

    @staticmethod
    async def update_ticket_internal(
        session: AsyncSession,
        organization_id: uuid.UUID,
        ticket_id: uuid.UUID,
        payload: TicketUpdateRequest,
        actor_id: str | None = None,
        actor_type: AuthorType = AuthorType.SYSTEM,
        auto_commit: bool = True,
    ) -> Ticket:
        """Internal ticket update logic for background processing and automated workflows."""
        query = select(Ticket).where(
            Ticket.organization_id == organization_id,
            Ticket.id == ticket_id,
        )
        res = await session.execute(query)
        ticket = res.scalar_one_or_none()
        if not ticket:
            raise ResourceNotFoundException("Ticket", ticket_id)

        # 1. Optimistic Concurrency Control Check
        if payload.lock_version is not None and ticket.lock_version != payload.lock_version:
            raise ConflictException(
                "Ticket was modified by another user. Please reload the latest ticket state.",
                code="CONCURRENCY_CONFLICT",
            )

        events_to_create: list[TicketEvent] = []
        has_mutations = False

        # 2. Subject update
        if payload.subject is not None and payload.subject.strip() != ticket.subject:
            ticket.subject = payload.subject.strip()
            has_mutations = True

        # 3. Status transition
        if payload.status is not None and payload.status != ticket.status:
            if not can_transition_ticket_status(ticket.status, payload.status):
                raise ConflictException(
                    f"Invalid status transition from '{ticket.status}' to '{payload.status}'.",
                    code="INVALID_STATUS_TRANSITION",
                )
            old_status = ticket.status
            ticket.status = payload.status
            has_mutations = True

            if payload.status == TicketStatus.RESOLVED and not ticket.resolved_at:
                ticket.resolved_at = datetime.now(UTC)
            elif payload.status == TicketStatus.CLOSED and not ticket.closed_at:
                ticket.closed_at = datetime.now(UTC)

            events_to_create.append(
                TicketEvent(
                    organization_id=organization_id,
                    ticket_id=ticket.id,
                    event_type=TicketEventType.STATUS_CHANGED,
                    event_timestamp=datetime.now(UTC),
                    actor_type=actor_type,
                    actor_id=actor_id or "system",
                    previous_value={"status": old_status},
                    new_value={"status": payload.status},
                    correlation_id=correlation_id_ctx.get(),
                )
            )

        # 4. Priority change
        if payload.priority is not None and payload.priority != ticket.priority:
            old_priority = ticket.priority
            ticket.priority = payload.priority
            has_mutations = True

            events_to_create.append(
                TicketEvent(
                    organization_id=organization_id,
                    ticket_id=ticket.id,
                    event_type=TicketEventType.PRIORITY_CHANGED,
                    event_timestamp=datetime.now(UTC),
                    actor_type=actor_type,
                    actor_id=actor_id or "system",
                    previous_value={"priority": old_priority},
                    new_value={"priority": payload.priority},
                    correlation_id=correlation_id_ctx.get(),
                )
            )

        # 5. Assignment change
        if payload.assigned_actor_id is not None:
            new_assignee = (
                payload.assigned_actor_id.strip() if payload.assigned_actor_id.strip() else None
            )
            if new_assignee != ticket.assigned_actor_id:
                old_assignee = ticket.assigned_actor_id
                ticket.assigned_actor_id = new_assignee
                has_mutations = True

                events_to_create.append(
                    TicketEvent(
                        organization_id=organization_id,
                        ticket_id=ticket.id,
                        event_type=TicketEventType.ASSIGNMENT_CHANGED,
                        event_timestamp=datetime.now(UTC),
                        actor_type=actor_type,
                        actor_id=actor_id or "system",
                        previous_value={"assigned_actor_id": old_assignee},
                        new_value={"assigned_actor_id": new_assignee},
                        correlation_id=correlation_id_ctx.get(),
                    )
                )

        # 6. Customer change
        if payload.customer_id is not None and payload.customer_id != ticket.customer_id:
            old_cust = ticket.customer_id
            ticket.customer_id = payload.customer_id
            has_mutations = True

            events_to_create.append(
                TicketEvent(
                    organization_id=organization_id,
                    ticket_id=ticket.id,
                    event_type=TicketEventType.CUSTOMER_LINKED,
                    event_timestamp=datetime.now(UTC),
                    actor_type=actor_type,
                    actor_id=actor_id or "system",
                    previous_value={"customer_id": str(old_cust) if old_cust else None},
                    new_value={"customer_id": str(payload.customer_id)},
                    correlation_id=correlation_id_ctx.get(),
                )
            )

        if has_mutations:
            ticket.lock_version += 1
            for ev in events_to_create:
                session.add(ev)
            if auto_commit:
                await session.commit()
                try:
                    await set_tenant_rls_context(session, organization_id)
                except Exception:
                    pass
                await session.refresh(ticket)
            else:
                await session.flush()
            logger.info(f"Updated ticket {ticket.ticket_reference} (version {ticket.lock_version})")

        return ticket

    @staticmethod
    async def update_ticket(
        session: AsyncSession,
        context: OrganizationContext,
        ticket_id: uuid.UUID,
        payload: TicketUpdateRequest,
    ) -> Ticket:
        """Update mutable ticket fields with OCC validation, status rules, and atomic lifecycle events."""
        if not context.has_permission(Permission.TICKETS_WRITE):
            raise ForbiddenException("Permission 'tickets:write' required to update tickets.")

        org_id = context.organization.id
        if payload.assigned_actor_id is not None:
            new_assignee = (
                payload.assigned_actor_id.strip() if payload.assigned_actor_id.strip() else None
            )
            if not context.has_permission(Permission.TICKETS_ASSIGN):
                raise ForbiddenException(
                    "Permission 'tickets:assign' required to reassign tickets."
                )
            if new_assignee:
                await TicketService.validate_assignee(session, org_id, new_assignee)

        if payload.customer_id is not None:
            customer = await context.tenant_query.get_customer(payload.customer_id)
            if not customer:
                raise ResourceNotFoundException("Customer", payload.customer_id)

        return await TicketService.update_ticket_internal(
            session=session,
            organization_id=org_id,
            ticket_id=ticket_id,
            payload=payload,
            actor_id=str(context.user.id),
            actor_type=AuthorType.AGENT,
            auto_commit=True,
        )

    @staticmethod
    async def list_ticket_events(
        session: AsyncSession,
        context: OrganizationContext,
        ticket_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[TicketEvent], int]:
        """List historical lifecycle events for a ticket in deterministic chronological order."""
        if not context.has_permission(Permission.TICKETS_READ):
            raise ForbiddenException("Permission 'tickets:read' required to view ticket history.")

        org_id = context.organization.id
        # Verify ticket belongs to this organization
        ticket = await context.tenant_query.get_ticket(ticket_id)
        if not ticket:
            raise ResourceNotFoundException("Ticket", ticket_id)

        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        count_stmt = select(func.count(TicketEvent.id)).where(
            TicketEvent.organization_id == org_id,
            TicketEvent.ticket_id == ticket_id,
        )
        total = (await session.execute(count_stmt)).scalar_one()

        query = (
            select(TicketEvent)
            .where(
                TicketEvent.organization_id == org_id,
                TicketEvent.ticket_id == ticket_id,
            )
            .order_by(TicketEvent.event_timestamp.asc(), TicketEvent.id.asc())
            .limit(limit)
            .offset(offset)
        )
        res = await session.execute(query)
        items = list(res.scalars().all())
        return items, total
