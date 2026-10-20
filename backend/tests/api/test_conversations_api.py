"""API tests for conversation threads, deterministic message sequencing, idempotency, and attachments."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.enums import (
    AttachmentScanStatus,
    ConversationStatus,
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
async def conv_test_context() -> AsyncIterator[
    tuple[AsyncClient, AsyncSession, Organization, User, Ticket, Conversation]
]:
    """Create test environment with organization, agent user, ticket, and initial conversation."""
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
        # Organization
        org = Organization(
            name="OmniCorp Support", slug="omnicorp-support", status=OrganizationStatus.ACTIVE
        )
        db.add(org)
        await db.flush()

        # User
        user = User(
            email="agent.dave@omnicorp.com",
            password_hash=hash_password("SafeDave123!"),
            display_name="Dave Agent",
            status=UserStatus.ACTIVE,
        )
        db.add(user)
        await db.flush()

        # Membership
        mem = OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            role=MembershipRole.AGENT,
            status=MembershipStatus.ACTIVE,
        )
        db.add(mem)
        await db.flush()

        # Ticket
        ticket = Ticket(
            organization_id=org.id,
            ticket_number=1,
            ticket_reference="TICK-1",
            subject="Network latency investigation",
            status=TicketStatus.OPEN,
            priority=TicketPriority.HIGH,
            channel=TicketChannel.EMAIL,
            lock_version=1,
        )
        db.add(ticket)
        await db.flush()

        # Conversation
        conv = Conversation(
            organization_id=org.id,
            ticket_id=ticket.id,
            channel_type=TicketChannel.EMAIL,
            status=ConversationStatus.ACTIVE,
        )
        db.add(conv)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with session_factory() as db:
            yield client, db, org, user, ticket, conv

    app.dependency_overrides.clear()
    await engine.dispose()


async def login_as(client: AsyncClient, email: str, password: str = "SafeDave123!") -> None:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_message_creation_and_deterministic_order(conv_test_context):
    """Verify messages receive sequential sequence numbers and are returned in chronological order."""
    client, db, org, user, ticket, conv = conv_test_context
    await login_as(client, user.email)

    # Post message 1
    res1 = await client.post(
        f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages",
        json={"body_text": "First response from Dave"},
    )
    assert res1.status_code == 201
    assert res1.json()["sequence_number"] == 1
    assert res1.json()["author_type"] == "agent"

    # Post message 2
    res2 = await client.post(
        f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages",
        json={"body_text": "Follow-up clarification note"},
    )
    assert res2.status_code == 201
    assert res2.json()["sequence_number"] == 2

    # List messages
    list_res = await client.get(f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) == 2
    assert items[0]["sequence_number"] == 1
    assert items[1]["sequence_number"] == 2
    assert items[0]["body_text"] == "First response from Dave"


@pytest.mark.asyncio
async def test_message_external_id_idempotency(conv_test_context):
    """Verify submitting identical external_message_id returns existing record without duplicate creation."""
    client, db, org, user, ticket, conv = conv_test_context
    await login_as(client, user.email)

    ext_id = f"provider-msg-{uuid.uuid4()}"
    payload = {
        "body_text": "Idempotent communication attempt",
        "external_message_id": ext_id,
    }

    # First delivery
    res1 = await client.post(
        f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages",
        json=payload,
    )
    assert res1.status_code == 201
    msg1_id = res1.json()["id"]

    # Duplicate delivery
    res2 = await client.post(
        f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages",
        json=payload,
    )
    assert res2.status_code == 201
    msg2_id = res2.json()["id"]

    # IDs must match, proving idempotency
    assert msg1_id == msg2_id

    # List messages must only contain 1 record
    list_res = await client.get(f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages")
    assert list_res.json()["total"] == 1


@pytest.mark.asyncio
async def test_message_author_impersonation_prevention(conv_test_context):
    """Verify ordinary agent cannot submit messages as 'system' or 'ai'."""
    client, db, org, user, ticket, conv = conv_test_context
    await login_as(client, user.email)

    payload = {
        "body_text": "Unauthorized system broadcast",
        "author_type": "system",
    }
    res = await client.post(
        f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages",
        json=payload,
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_attachment_metadata_retrieval(conv_test_context):
    """Verify attachment metadata is retrieved safely without leaking storage_key."""
    client, db, org, user, ticket, conv = conv_test_context
    await login_as(client, user.email)

    # 1. Post a message
    msg_res = await client.post(
        f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages",
        json={"body_text": "Please see error log attached."},
    )
    msg_id = uuid.UUID(msg_res.json()["id"])

    # 2. Attach metadata record in DB
    att = Attachment(
        organization_id=org.id,
        message_id=msg_id,
        filename="server_error.log",
        storage_key="s3://supportgpt-private-vault/internal-key-99827",
        content_type="text/plain",
        size_bytes=4096,
        checksum_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        scan_status=AttachmentScanStatus.READY,
    )
    db.add(att)
    await db.commit()

    # 3. Retrieve attachments via API
    att_res = await client.get(
        f"/api/v1/organizations/{org.id}/conversations/{conv.id}/messages/{msg_id}/attachments"
    )
    assert att_res.status_code == 200
    items = att_res.json()["items"]
    assert len(items) == 1
    assert items[0]["filename"] == "server_error.log"
    assert items[0]["size_bytes"] == 4096
    assert items[0]["scan_status"] == "ready"

    # CRITICAL: Verify internal storage_key is NOT exposed in the payload
    assert "storage_key" not in items[0]
