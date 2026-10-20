"""API and database tests verifying multi-tenant isolation, cross-tenant access denial, and direct-ID defense."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import generate_session_token, hash_password, hash_session_token
from app.db.base import Base
from app.db.session import get_db_session
from app.db.tenant import TenantScopedQuery
from app.main import create_application
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import (
    AuthorType,
    CustomerStatus,
    MembershipRole,
    MembershipStatus,
    MessageDirection,
    OrganizationStatus,
    TicketChannel,
    TicketPriority,
    TicketStatus,
    UserStatus,
)
from app.models.membership import OrganizationMembership
from app.models.message import Message
from app.models.organization import Organization
from app.models.session import UserSession
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.user import User


@pytest.fixture
async def multi_tenant_fixture() -> AsyncIterator[dict]:
    """Provision two isolated organizations, respective users, tickets, and customers."""
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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with session_factory() as db:
            # 1. Organization A (Tenant Alpha)
            org_a = Organization(
                name="Tenant Alpha", slug="tenant-alpha", status=OrganizationStatus.ACTIVE
            )
            db.add(org_a)

            # 2. Organization B (Tenant Beta)
            org_b = Organization(
                name="Tenant Beta", slug="tenant-beta", status=OrganizationStatus.ACTIVE
            )
            db.add(org_b)
            await db.flush()

            # 3. User A (Owner of Alpha)
            user_a = User(
                email="alice@alpha.io",
                password_hash=hash_password("Pass123!"),
                display_name="Alice Alpha",
                status=UserStatus.ACTIVE,
            )
            # 4. User B (Owner of Beta)
            user_b = User(
                email="bob@beta.io",
                password_hash=hash_password("Pass123!"),
                display_name="Bob Beta",
                status=UserStatus.ACTIVE,
            )
            db.add_all([user_a, user_b])
            await db.flush()

            # 5. Memberships
            m_a = OrganizationMembership(
                organization_id=org_a.id,
                user_id=user_a.id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
            m_b = OrganizationMembership(
                organization_id=org_b.id,
                user_id=user_b.id,
                role=MembershipRole.OWNER,
                status=MembershipStatus.ACTIVE,
            )
            db.add_all([m_a, m_b])

            # 6. Sessions
            token_a = generate_session_token()
            token_b = generate_session_token()
            sess_a = UserSession(
                user_id=user_a.id,
                session_token_hash=hash_session_token(token_a),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            sess_b = UserSession(
                user_id=user_b.id,
                session_token_hash=hash_session_token(token_b),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            db.add_all([sess_a, sess_b])

            # 7. Customer & Ticket data in Tenant Alpha
            cust_a = Customer(
                organization_id=org_a.id,
                external_customer_id="cust-a-1",
                display_name="Alpha Customer",
                status=CustomerStatus.ACTIVE,
            )
            db.add(cust_a)
            await db.flush()

            ticket_a = Ticket(
                organization_id=org_a.id,
                customer_id=cust_a.id,
                ticket_number=1,
                ticket_reference="ALPHA-1",
                subject="Alpha Ticket 1",
                status=TicketStatus.OPEN,
                priority=TicketPriority.MEDIUM,
                channel=TicketChannel.WEB,
            )
            db.add(ticket_a)
            await db.flush()

            conv_a = Conversation(organization_id=org_a.id, ticket_id=ticket_a.id)
            db.add(conv_a)
            await db.flush()

            msg_a = Message(
                organization_id=org_a.id,
                conversation_id=conv_a.id,
                direction=MessageDirection.INBOUND,
                author_type=AuthorType.CUSTOMER,
                body_text="Hello Alpha",
            )
            db.add(msg_a)
            await db.flush()

            att_a = Attachment(
                organization_id=org_a.id,
                message_id=msg_a.id,
                filename="alpha_log.txt",
                content_type="text/plain",
                size_bytes=1024,
                storage_key="s3://alpha/log.txt",
            )
            event_a = TicketEvent(
                organization_id=org_a.id,
                ticket_id=ticket_a.id,
                event_type="created",
                actor_type=AuthorType.CUSTOMER,
            )
            db.add_all([att_a, event_a])

            # 8. Customer & Ticket data in Tenant Beta
            cust_b = Customer(
                organization_id=org_b.id,
                external_customer_id="cust-b-1",
                display_name="Beta Customer",
                status=CustomerStatus.ACTIVE,
            )
            db.add(cust_b)
            await db.flush()

            ticket_b = Ticket(
                organization_id=org_b.id,
                customer_id=cust_b.id,
                ticket_number=1,
                ticket_reference="BETA-1",
                subject="Beta Ticket 1",
                status=TicketStatus.OPEN,
                priority=TicketPriority.HIGH,
                channel=TicketChannel.EMAIL,
            )
            db.add(ticket_b)
            await db.commit()

            yield {
                "client": client,
                "db": db,
                "org_a": org_a,
                "org_b": org_b,
                "token_a": token_a,
                "token_b": token_b,
                "ticket_a": ticket_a,
                "ticket_b": ticket_b,
                "cust_a": cust_a,
                "cust_b": cust_b,
                "conv_a": conv_a,
                "msg_a": msg_a,
                "att_a": att_a,
                "event_a": event_a,
            }

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_organization_access_forbidden(multi_tenant_fixture: dict):
    """Verify that User A cannot read or manage members of Organization B."""
    client = multi_tenant_fixture["client"]
    org_b = multi_tenant_fixture["org_b"]
    token_a = multi_tenant_fixture["token_a"]

    # User A tries to list members of Org B
    response = await client.get(
        f"/api/v1/organizations/{org_b.id}/members",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "PERMISSION_DENIED"
    assert "not hold an active membership" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_cross_tenant_membership_me_forbidden(multi_tenant_fixture: dict):
    """Verify that User A querying /memberships/me for Org B is denied."""
    client = multi_tenant_fixture["client"]
    org_b = multi_tenant_fixture["org_b"]
    token_a = multi_tenant_fixture["token_a"]

    response = await client.get(
        f"/api/v1/organizations/{org_b.id}/memberships/me",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(multi_tenant_fixture: dict):
    """Verify that unauthenticated requests to organization endpoints return 401."""
    client = multi_tenant_fixture["client"]
    org_a = multi_tenant_fixture["org_a"]

    response = await client.get(f"/api/v1/organizations/{org_a.id}/members")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_direct_object_id_attack_resistance_via_tenant_query(multi_tenant_fixture: dict):
    """Verify that TenantScopedQuery prevents cross-tenant entity access even with valid IDs."""
    db = multi_tenant_fixture["db"]
    org_a = multi_tenant_fixture["org_a"]
    org_b = multi_tenant_fixture["org_b"]
    ticket_a = multi_tenant_fixture["ticket_a"]
    ticket_b = multi_tenant_fixture["ticket_b"]
    cust_a = multi_tenant_fixture["cust_a"]
    cust_b = multi_tenant_fixture["cust_b"]
    conv_a = multi_tenant_fixture["conv_a"]
    msg_a = multi_tenant_fixture["msg_a"]
    att_a = multi_tenant_fixture["att_a"]
    event_a = multi_tenant_fixture["event_a"]

    # Scoped to Tenant Alpha
    query_alpha = TenantScopedQuery(db, org_a.id)

    # 1. Alpha can read Alpha's ticket and customer
    assert (await query_alpha.get_ticket(ticket_a.id)) is not None
    assert (await query_alpha.get_customer(cust_a.id)) is not None
    assert (await query_alpha.get_conversation(conv_a.id)) is not None
    assert (await query_alpha.get_message(msg_a.id)) is not None
    assert (await query_alpha.get_attachment(att_a.id)) is not None
    assert (await query_alpha.get_ticket_event(event_a.id)) is not None

    # 2. Direct ID attack: Alpha attempts to read Beta's ticket and customer
    assert (await query_alpha.get_ticket(ticket_b.id)) is None
    assert (await query_alpha.get_customer(cust_b.id)) is None

    # 3. Scoped to Tenant Beta
    query_beta = TenantScopedQuery(db, org_b.id)

    # 4. Direct ID attack: Beta attempts to read Alpha's ticket and customer
    assert (await query_beta.get_ticket(ticket_a.id)) is None
    assert (await query_beta.get_customer(cust_a.id)) is None
    assert (await query_beta.get_conversation(conv_a.id)) is None
    assert (await query_beta.get_message(msg_a.id)) is None
    assert (await query_beta.get_attachment(att_a.id)) is None
    assert (await query_beta.get_ticket_event(event_a.id)) is None

    # 5. Non-existent UUID returns None
    random_uuid = uuid.uuid4()
    assert (await query_alpha.get_ticket(random_uuid)) is None
