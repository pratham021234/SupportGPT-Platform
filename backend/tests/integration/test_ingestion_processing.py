"""Integration tests verifying background worker execution, domain mapping, deduplication, and crash recovery."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import (
    AuthorType,
    IngestionStatus,
    MessageDirection,
    OrganizationStatus,
    SourceProvider,
    SourceStatus,
    TicketStatus,
)
from app.models.event_source import EventSource
from app.models.ingestion_receipt import IngestionReceipt
from app.models.message import Message
from app.models.organization import Organization
from app.models.ticket import Ticket
from app.services.ingestion_worker import IngestionWorker


@pytest.fixture
async def worker_context() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], Organization, EventSource]
]:
    """Setup SQLite database and sessionmaker for background worker testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = ON;"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        org = Organization(
            name="Worker Test Org", slug="worker-test-org", status=OrganizationStatus.ACTIVE
        )
        db.add(org)
        await db.flush()

        source = EventSource(
            organization_id=org.id,
            name="Inbound Support Webhook",
            provider=SourceProvider.GENERIC_WEBHOOK,
            status=SourceStatus.ACTIVE,
            signing_secret_hash="hash",
            supported_event_types=["ticket.created", "message.received"],
        )
        db.add(source)
        await db.commit()
        await db.refresh(org)
        await db.refresh(source)

    yield session_factory, org, source
    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_processes_ticket_created_event(worker_context):
    """Worker claims queued ticket.created event, creates domain Ticket & Customer, and marks receipt PROCESSED."""
    session_factory, org, source = worker_context
    worker = IngestionWorker(session_factory=session_factory)

    # 1. Enqueue an inbound event receipt
    now = datetime.now(UTC)
    async with session_factory() as db:
        receipt = IngestionReceipt(
            organization_id=org.id,
            source_id=source.id,
            source_provider=source.provider,
            external_event_id="evt-ticket-001",
            event_type="ticket.created",
            status=IngestionStatus.QUEUED,
            received_at=now,
            next_attempt_at=now,
            payload={
                "event_id": "evt-ticket-001",
                "event_type": "ticket.created",
                "subject": "VPN Access Revoked",
                "description": "I cannot connect to the corporate VPN.",
                "customer": {
                    "email": "sam@external.com",
                    "name": "Sam Smith",
                },
                "ticket": {
                    "id": "ext-tick-999",
                },
            },
        )
        db.add(receipt)
        await db.commit()
        receipt_id = receipt.id

    # 2. Worker executes single cycle
    stats = await worker.run_once()
    assert stats["claimed"] == 1
    assert stats["processed"] == 1
    assert stats["failed"] == 0

    # 3. Verify receipt status
    async with session_factory() as db:
        res = await db.execute(select(IngestionReceipt).where(IngestionReceipt.id == receipt_id))
        updated_receipt = res.scalar_one()
        assert updated_receipt.status == IngestionStatus.PROCESSED
        assert updated_receipt.processed_at is not None
        assert updated_receipt.error_code is None

        # 4. Verify domain Ticket creation
        tick_res = await db.execute(
            select(Ticket).where(
                Ticket.organization_id == org.id,
                Ticket.external_reference == "ext-tick-999",
            )
        )
        ticket = tick_res.scalar_one_or_none()
        assert ticket is not None
        assert ticket.subject == "VPN Access Revoked"
        assert ticket.status == TicketStatus.OPEN

        # 5. Verify Customer created
        cust_res = await db.execute(select(Customer).where(Customer.id == ticket.customer_id))
        customer = cust_res.scalar_one_or_none()
        assert customer is not None
        assert customer.display_name == "Sam Smith"


@pytest.mark.asyncio
async def test_worker_processes_inbound_message_event(worker_context):
    """Worker appends message to existing ticket's conversation thread."""
    session_factory, org, source = worker_context
    worker = IngestionWorker(session_factory=session_factory)

    # 1. Create a ticket first
    async with session_factory() as db:
        ticket = Ticket(
            organization_id=org.id,
            ticket_number="TICK-100",
            ticket_reference="REF-TICK-100",
            subject="Existing Ticket",
            external_reference="ext-thread-555",
            status=TicketStatus.OPEN,
        )
        db.add(ticket)
        await db.flush()

        conv = Conversation(
            organization_id=org.id,
            ticket_id=ticket.id,
        )
        db.add(conv)
        await db.flush()

        # Enqueue message event
        now = datetime.now(UTC)
        receipt = IngestionReceipt(
            organization_id=org.id,
            source_id=source.id,
            source_provider=source.provider,
            external_event_id="evt-msg-001",
            event_type="message.received",
            status=IngestionStatus.QUEUED,
            received_at=now,
            next_attempt_at=now,
            payload={
                "event_id": "evt-msg-001",
                "event_type": "message.received",
                "ticket_id": "ext-thread-555",
                "message_id": "ext-msg-101",
                "body": "Thank you for the update, here are logs.",
            },
        )
        db.add(receipt)
        await db.commit()

    # 2. Worker executes
    stats = await worker.run_once()
    assert stats["processed"] == 1

    # 3. Verify Message was appended
    async with session_factory() as db:
        msg_res = await db.execute(
            select(Message).where(Message.external_message_id == "ext-msg-101")
        )
        message = msg_res.scalar_one_or_none()
        assert message is not None
        assert message.body_text == "Thank you for the update, here are logs."
        assert message.direction == MessageDirection.INBOUND
        assert message.author_type == AuthorType.CUSTOMER


@pytest.mark.asyncio
async def test_worker_lease_expiration_crash_recovery(worker_context):
    """Hung processing job with expired lease is reclaimed by next worker pass."""
    session_factory, org, source = worker_context
    worker = IngestionWorker(session_factory=session_factory)

    now = datetime.now(UTC)
    hung_time = now - timedelta(seconds=600)  # 10 minutes ago (> 300s lease timeout)

    # Insert a receipt stuck in PROCESSING from a crashed worker
    async with session_factory() as db:
        hung_receipt = IngestionReceipt(
            organization_id=org.id,
            source_id=source.id,
            source_provider=source.provider,
            external_event_id="evt-hung-001",
            event_type="ticket.created",
            status=IngestionStatus.PROCESSING,
            received_at=hung_time,
            processing_started_at=hung_time,
            locked_by="crashed-worker-pid-9999",
            attempt_count=1,
            payload={
                "event_id": "evt-hung-001",
                "event_type": "ticket.created",
                "subject": "Recovered Ticket",
                "description": "Successfully recovered from crashed worker.",
                "ticket": {"id": "ext-recovered-1"},
            },
        )
        db.add(hung_receipt)
        await db.commit()
        receipt_id = hung_receipt.id

    # New worker runs
    stats = await worker.run_once()
    assert stats["claimed"] == 1
    assert stats["processed"] == 1

    async with session_factory() as db:
        res = await db.execute(select(IngestionReceipt).where(IngestionReceipt.id == receipt_id))
        rec = res.scalar_one()
        assert rec.status == IngestionStatus.PROCESSED
        assert rec.attempt_count == 2
        assert rec.locked_by is None


@pytest.mark.asyncio
async def test_worker_permanent_failure_transitions_to_dead_letter(worker_context):
    """Unrecoverable normalization failure transitions receipt directly to DEAD_LETTER."""
    session_factory, org, source = worker_context
    worker = IngestionWorker(session_factory=session_factory)

    now = datetime.now(UTC)
    async with session_factory() as db:
        # Malformed payload lacking event_id
        bad_receipt = IngestionReceipt(
            organization_id=org.id,
            source_id=source.id,
            source_provider=source.provider,
            external_event_id="evt-bad-001",
            event_type="unknown.event",
            status=IngestionStatus.QUEUED,
            received_at=now,
            next_attempt_at=now,
            payload={"no_event_id_here": True},
        )
        db.add(bad_receipt)
        await db.commit()
        receipt_id = bad_receipt.id

    stats = await worker.run_once()
    assert stats["claimed"] == 1
    assert stats["failed"] == 1

    async with session_factory() as db:
        res = await db.execute(select(IngestionReceipt).where(IngestionReceipt.id == receipt_id))
        rec = res.scalar_one()
        assert rec.status == IngestionStatus.DEAD_LETTER
        assert rec.error_code == "NORMALIZATION_FAILED"
        assert rec.locked_by is None
