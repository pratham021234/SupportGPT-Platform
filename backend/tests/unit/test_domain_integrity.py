"""Database integrity tests validating foreign keys, constraints, and unique indexes in an isolated engine."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity
from app.models.enums import (
    AuthorType,
    CustomerStatus,
    IdentityType,
    MessageDirection,
    OrganizationStatus,
    TicketChannel,
    TicketPriority,
    TicketStatus,
)
from app.models.ingestion_receipt import IngestionReceipt
from app.models.message import Message
from app.models.organization import (
    Organization,
    allocate_next_ticket_number,
)
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent


@pytest.fixture
async def async_test_session():
    """In-memory SQLite async engine with foreign key enforcement enabled."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        # Enforce foreign key constraints in SQLite
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_end_to_end_domain_lifecycle(async_test_session: AsyncSession):
    """Verify full creation, relationship chaining, and atomic ticket allocation."""
    session = async_test_session

    # 1. Create Organization
    org = Organization(name="Acme Corp", slug="acme-corp", status=OrganizationStatus.ACTIVE)
    session.add(org)
    await session.flush()
    assert org.id is not None

    # 2. Concurrency-safe atomic ticket number allocation
    ticket_num_1 = await allocate_next_ticket_number(session, org.id)
    ticket_num_2 = await allocate_next_ticket_number(session, org.id)
    assert ticket_num_1 == 1
    assert ticket_num_2 == 2

    # 3. Create Customer
    customer = Customer(
        organization_id=org.id,
        display_name="Sarah Connor",
        company_name="Cyberdyne",
        status=CustomerStatus.ACTIVE,
    )
    session.add(customer)
    await session.flush()

    # 4. Attach multiple Customer Identities (Email + Phone)
    email_ident = CustomerIdentity(
        organization_id=org.id,
        customer_id=customer.id,
        identity_type=IdentityType.EMAIL,
        normalized_value="sarah@cyberdyne.com",
    )
    phone_ident = CustomerIdentity(
        organization_id=org.id,
        customer_id=customer.id,
        identity_type=IdentityType.PHONE,
        normalized_value="+15550199",
    )
    session.add_all([email_ident, phone_ident])
    await session.flush()

    # 5. Create Ticket
    ticket = Ticket(
        organization_id=org.id,
        customer_id=customer.id,
        ticket_number=ticket_num_1,
        ticket_reference=f"TICK-{ticket_num_1}",
        subject="Critical inquiry regarding neural net",
        status=TicketStatus.OPEN,
        priority=TicketPriority.URGENT,
        channel=TicketChannel.EMAIL,
    )
    session.add(ticket)
    await session.flush()

    # 6. Create Conversation thread
    conversation = Conversation(
        organization_id=org.id,
        ticket_id=ticket.id,
        channel_type=TicketChannel.EMAIL,
        external_thread_id="th_email_001",
    )
    session.add(conversation)
    await session.flush()

    # 7. Create Inbound Message
    msg = Message(
        organization_id=org.id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        author_type=AuthorType.CUSTOMER,
        author_id=str(customer.id),
        body_text="System needs immediate verification.",
        sequence_number=1,
    )
    session.add(msg)
    await session.flush()

    # 8. Create Attachment metadata
    attachment = Attachment(
        organization_id=org.id,
        message_id=msg.id,
        filename="log_dump.txt",
        storage_key=f"org/{org.id}/msg/{msg.id}/log_dump.txt",
        content_type="text/plain",
        size_bytes=5120,
    )
    session.add(attachment)
    await session.flush()

    # 9. Create Lifecycle Audit Event
    event = TicketEvent(
        organization_id=org.id,
        ticket_id=ticket.id,
        event_type="created",
        actor_type=AuthorType.CUSTOMER,
        actor_id=str(customer.id),
        payload={"initial_channel": "email"},
    )
    session.add(event)
    await session.commit()

    # Query back and verify integrity
    persisted_ticket = await session.get(Ticket, ticket.id)
    assert persisted_ticket is not None
    assert persisted_ticket.ticket_reference == "TICK-1"
    assert persisted_ticket.customer_id == customer.id


@pytest.mark.asyncio
async def test_organization_slug_uniqueness(async_test_session: AsyncSession):
    """Verify that duplicate organization slugs are strictly rejected."""
    session = async_test_session

    org1 = Organization(name="Org One", slug="shared-slug", status=OrganizationStatus.ACTIVE)
    session.add(org1)
    await session.commit()

    org2 = Organization(name="Org Two", slug="shared-slug", status=OrganizationStatus.ACTIVE)
    session.add(org2)
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_customer_identity_uniqueness_scoped_to_organization(
    async_test_session: AsyncSession,
):
    """Verify duplicate identity is rejected in same organization but allowed across organizations."""
    session = async_test_session

    org_a = Organization(name="Org A", slug="org-a", status=OrganizationStatus.ACTIVE)
    org_b = Organization(name="Org B", slug="org-b", status=OrganizationStatus.ACTIVE)
    session.add_all([org_a, org_b])
    await session.flush()

    cust_a = Customer(organization_id=org_a.id, display_name="Cust A")
    cust_b = Customer(organization_id=org_b.id, display_name="Cust B")
    session.add_all([cust_a, cust_b])
    await session.flush()

    org_a_id = org_a.id
    org_b_id = org_b.id
    cust_a_id = cust_a.id
    cust_b_id = cust_b.id

    # Register email in Org A
    id_a = CustomerIdentity(
        organization_id=org_a_id,
        customer_id=cust_a_id,
        identity_type=IdentityType.EMAIL,
        normalized_value="user@example.com",
    )
    session.add(id_a)
    await session.commit()

    # Duplicate registration in Org A MUST fail
    id_a_dup = CustomerIdentity(
        organization_id=org_a_id,
        customer_id=cust_a_id,
        identity_type=IdentityType.EMAIL,
        normalized_value="user@example.com",
    )
    session.add(id_a_dup)
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()

    # Legitimate registration of identical email in Org B MUST succeed
    id_b = CustomerIdentity(
        organization_id=org_b_id,
        customer_id=cust_b_id,
        identity_type=IdentityType.EMAIL,
        normalized_value="user@example.com",
    )
    session.add(id_b)
    await session.commit()
    assert id_b.id is not None


@pytest.mark.asyncio
async def test_ingestion_receipt_idempotency_constraint(async_test_session: AsyncSession):
    """Verify duplicate provider event IDs are rejected within the same organization."""
    session = async_test_session

    org = Organization(name="Org Ingest", slug="org-ingest", status=OrganizationStatus.ACTIVE)
    session.add(org)
    await session.flush()

    receipt_1 = IngestionReceipt(
        organization_id=org.id,
        source_provider="sendgrid",
        external_event_id="evt_unique_12345",
        event_type="inbound_email",
    )
    session.add(receipt_1)
    await session.commit()

    # Duplicate receipt
    receipt_2 = IngestionReceipt(
        organization_id=org.id,
        source_provider="sendgrid",
        external_event_id="evt_unique_12345",
        event_type="inbound_email",
    )
    session.add(receipt_2)
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_attachment_size_check_constraint(async_test_session: AsyncSession):
    """Verify negative attachment size raises a check constraint IntegrityError."""
    session = async_test_session

    org = Organization(name="Org Att", slug="org-att", status=OrganizationStatus.ACTIVE)
    session.add(org)
    await session.flush()

    ticket = Ticket(
        organization_id=org.id,
        ticket_number=1,
        ticket_reference="TICK-1",
        subject="File test",
    )
    session.add(ticket)
    await session.flush()

    conv = Conversation(organization_id=org.id, ticket_id=ticket.id)
    session.add(conv)
    await session.flush()

    msg = Message(
        organization_id=org.id,
        conversation_id=conv.id,
        direction=MessageDirection.INBOUND,
        author_type=AuthorType.CUSTOMER,
        body_text="Here is negative file",
    )
    session.add(msg)
    await session.flush()

    bad_att = Attachment(
        organization_id=org.id,
        message_id=msg.id,
        filename="corrupt.dat",
        storage_key="keys/bad.dat",
        content_type="application/octet-stream",
        size_bytes=-100,  # Negative bytes
    )
    session.add(bad_att)
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_foreign_key_deletion_restriction(async_test_session: AsyncSession):
    """Verify that deleting an organization with active customer records is restricted."""
    session = async_test_session

    org = Organization(name="Protected Org", slug="protected-org", status=OrganizationStatus.ACTIVE)
    session.add(org)
    await session.flush()

    cust = Customer(organization_id=org.id, display_name="Protected Customer")
    session.add(cust)
    await session.commit()

    # Attempt to delete Organization directly without cleaning up dependents
    await session.delete(org)
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
async def test_composite_tenant_boundary_consistency(async_test_session: AsyncSession):
    """Verify that a conversation cannot point to a ticket in a different organization."""
    session = async_test_session

    org_1 = Organization(name="Org One", slug="org-one", status=OrganizationStatus.ACTIVE)
    org_2 = Organization(name="Org Two", slug="org-two", status=OrganizationStatus.ACTIVE)
    session.add_all([org_1, org_2])
    await session.flush()

    ticket_in_org_1 = Ticket(
        organization_id=org_1.id,
        ticket_number=1,
        ticket_reference="TICK-1",
        subject="Org 1 issue",
    )
    session.add(ticket_in_org_1)
    await session.flush()

    # Attempt to create conversation in Org 2 pointing to Ticket in Org 1
    mismatched_conv = Conversation(
        organization_id=org_2.id,  # Mismatched organization!
        ticket_id=ticket_in_org_1.id,
    )
    session.add(mismatched_conv)
    with pytest.raises(IntegrityError):
        await session.commit()
