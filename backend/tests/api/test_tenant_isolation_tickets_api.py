"""Security tests verifying tenant isolation, cross-organization boundary defense, and direct-ID attack resistance."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import (
    ConversationStatus,
    CustomerStatus,
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
    TicketChannel,
    TicketPriority,
    TicketStatus,
    UserStatus,
)
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.ticket import Ticket
from app.models.user import User


@pytest.fixture
async def multi_tenant_tickets_context() -> AsyncIterator[dict]:
    """Provision two completely isolated organizations (Org A and Org B) with their own users and tickets."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    app = create_application()

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_get_db_session

    async with session_factory() as db:
        # Tenant 1: Alpha Corp
        org_a = Organization(name="Alpha Corp", slug="alpha-corp", status=OrganizationStatus.ACTIVE)
        user_a = User(
            email="agent@alpha.com",
            password_hash=hash_password("PassAlpha123!"),
            display_name="Alpha Agent",
            status=UserStatus.ACTIVE,
        )
        db.add_all([org_a, user_a])
        await db.flush()

        mem_a = OrganizationMembership(
            organization_id=org_a.id,
            user_id=user_a.id,
            role=MembershipRole.AGENT,
            status=MembershipStatus.ACTIVE,
        )
        customer_a = Customer(
            organization_id=org_a.id,
            display_name="Alpha Client",
            status=CustomerStatus.ACTIVE,
        )
        ticket_a = Ticket(
            organization_id=org_a.id,
            customer_id=customer_a.id,
            ticket_number=1,
            ticket_reference="TICK-1",
            subject="Alpha Private Support Ticket",
            status=TicketStatus.OPEN,
            priority=TicketPriority.MEDIUM,
            channel=TicketChannel.EMAIL,
            lock_version=1,
        )
        db.add_all([mem_a, customer_a, ticket_a])
        await db.flush()

        conv_a = Conversation(
            organization_id=org_a.id,
            ticket_id=ticket_a.id,
            channel_type=TicketChannel.EMAIL,
            status=ConversationStatus.ACTIVE,
        )
        db.add(conv_a)

        # Tenant 2: Beta Corp
        org_b = Organization(name="Beta Corp", slug="beta-corp", status=OrganizationStatus.ACTIVE)
        user_b = User(
            email="agent@beta.com",
            password_hash=hash_password("PassBeta123!"),
            display_name="Beta Agent",
            status=UserStatus.ACTIVE,
        )
        db.add_all([org_b, user_b])
        await db.flush()

        mem_b = OrganizationMembership(
            organization_id=org_b.id,
            user_id=user_b.id,
            role=MembershipRole.AGENT,
            status=MembershipStatus.ACTIVE,
        )
        customer_b = Customer(
            organization_id=org_b.id,
            display_name="Beta Client",
            status=CustomerStatus.ACTIVE,
        )
        ticket_b = Ticket(
            organization_id=org_b.id,
            customer_id=customer_b.id,
            ticket_number=1,
            ticket_reference="TICK-1",
            subject="Beta Secret Support Ticket",
            status=TicketStatus.OPEN,
            priority=TicketPriority.URGENT,
            channel=TicketChannel.EMAIL,
            lock_version=1,
        )
        db.add_all([mem_b, customer_b, ticket_b])
        await db.flush()

        conv_b = Conversation(
            organization_id=org_b.id,
            ticket_id=ticket_b.id,
            channel_type=TicketChannel.EMAIL,
            status=ConversationStatus.ACTIVE,
        )
        db.add(conv_b)

        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {
            "client": client,
            "org_a": org_a,
            "user_a": user_a,
            "ticket_a": ticket_a,
            "conv_a": conv_a,
            "customer_a": customer_a,
            "org_b": org_b,
            "user_b": user_b,
            "ticket_b": ticket_b,
            "conv_b": conv_b,
            "customer_b": customer_b,
        }

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_ticket_read_returns_404(multi_tenant_tickets_context):
    """Verify that Org A agent attempting to read Org B's ticket UUID returns 404 to avoid leaking existence."""
    ctx = multi_tenant_tickets_context
    client: AsyncClient = ctx["client"]

    # Log in as Alpha Agent
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": ctx["user_a"].email, "password": "PassAlpha123!"},
    )
    assert login_res.status_code == 200

    # Attempt to read Beta's ticket within Alpha's org scope -> Must return 404
    cross_read_res = await client.get(
        f"/api/v1/organizations/{ctx['org_a'].id}/tickets/{ctx['ticket_b'].id}"
    )
    assert cross_read_res.status_code == 404
    assert cross_read_res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_tenant_ticket_update_returns_404(multi_tenant_tickets_context):
    """Verify that Org A agent cannot update Org B's ticket."""
    ctx = multi_tenant_tickets_context
    client: AsyncClient = ctx["client"]

    await client.post(
        "/api/v1/auth/login",
        json={"email": ctx["user_a"].email, "password": "PassAlpha123!"},
    )

    # Attempt to patch Beta's ticket
    patch_res = await client.patch(
        f"/api/v1/organizations/{ctx['org_a'].id}/tickets/{ctx['ticket_b'].id}",
        json={"priority": "low"},
    )
    assert patch_res.status_code == 404
    assert patch_res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_tenant_customer_association_denied(multi_tenant_tickets_context):
    """Verify that Org A cannot link Org B's customer to an Org A ticket."""
    ctx = multi_tenant_tickets_context
    client: AsyncClient = ctx["client"]

    await client.post(
        "/api/v1/auth/login",
        json={"email": ctx["user_a"].email, "password": "PassAlpha123!"},
    )

    # Attempt to create ticket with Org B's customer_id
    res = await client.post(
        f"/api/v1/organizations/{ctx['org_a'].id}/tickets",
        json={
            "subject": "Attack attempt with foreign customer",
            "customer_id": str(ctx["customer_b"].id),
        },
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_tenant_assignment_denied(multi_tenant_tickets_context):
    """Verify that Org A cannot assign an agent from Org B."""
    ctx = multi_tenant_tickets_context
    client: AsyncClient = ctx["client"]

    await client.post(
        "/api/v1/auth/login",
        json={"email": ctx["user_a"].email, "password": "PassAlpha123!"},
    )

    # Attempt to assign Beta's agent to Alpha's ticket
    res = await client.patch(
        f"/api/v1/organizations/{ctx['org_a'].id}/tickets/{ctx['ticket_a'].id}",
        json={"assigned_actor_id": str(ctx["user_b"].id)},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "INVALID_ASSIGNEE"


@pytest.mark.asyncio
async def test_cross_tenant_conversation_and_messages_returns_404(multi_tenant_tickets_context):
    """Verify that Org A cannot access Org B's conversations or messages."""
    ctx = multi_tenant_tickets_context
    client: AsyncClient = ctx["client"]

    await client.post(
        "/api/v1/auth/login",
        json={"email": ctx["user_a"].email, "password": "PassAlpha123!"},
    )

    # Attempt to read Beta's conversation
    conv_res = await client.get(
        f"/api/v1/organizations/{ctx['org_a'].id}/conversations/{ctx['conv_b'].id}"
    )
    assert conv_res.status_code == 404

    # Attempt to post a message into Beta's conversation
    msg_res = await client.post(
        f"/api/v1/organizations/{ctx['org_a'].id}/conversations/{ctx['conv_b'].id}/messages",
        json={"body_text": "Intruder message"},
    )
    assert msg_res.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_event_history_denied(multi_tenant_tickets_context):
    """Verify that Org A cannot view Org B's ticket audit history."""
    ctx = multi_tenant_tickets_context
    client: AsyncClient = ctx["client"]

    await client.post(
        "/api/v1/auth/login",
        json={"email": ctx["user_a"].email, "password": "PassAlpha123!"},
    )

    res = await client.get(
        f"/api/v1/organizations/{ctx['org_a'].id}/tickets/{ctx['ticket_b'].id}/events"
    )
    assert res.status_code == 404
