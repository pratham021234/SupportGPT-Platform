"""API integration tests for inbound webhook reception, signatures, and idempotency."""

import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.enums import OrganizationStatus, SourceProvider, SourceStatus
from app.models.event_source import EventSource
from app.models.organization import Organization
from app.services.secret_resolver import SecretResolver


@pytest.fixture
async def webhook_context() -> AsyncIterator[
    tuple[AsyncClient, AsyncSession, Organization, EventSource, str]
]:
    """Setup in-memory SQLite database, FastAPI test client, and an active EventSource."""
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

    raw_secret = "whsec_super_secret_signing_key_12345"
    async with session_factory() as db:
        org = Organization(name="Webhook Org", slug="webhook-org", status=OrganizationStatus.ACTIVE)
        db.add(org)
        await db.flush()

        source = EventSource(
            organization_id=org.id,
            name="Production Inbound Webhook",
            provider=SourceProvider.GENERIC_WEBHOOK,
            status=SourceStatus.ACTIVE,
            signing_secret_hash=SecretResolver.hash_secret(raw_secret),
            signing_secret_encrypted=SecretResolver.encrypt_secret(raw_secret),
            signing_secret_preview=SecretResolver.make_preview(raw_secret),
            supported_event_types=["ticket.created", "message.received"],
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)
        await db.refresh(org)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, db, org, source, raw_secret

    await engine.dispose()


def _sign(body: bytes, secret: str) -> str:
    """Helper to compute valid HMAC-SHA256 signature."""
    hex_digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={hex_digest}"


@pytest.mark.asyncio
async def test_webhook_reception_success_and_queued(webhook_context):
    """Valid webhook creates receipt in QUEUED status and returns 202 Accepted."""
    client, _, _, source, secret = webhook_context

    payload = {
        "event_id": "evt-alpha-001",
        "event_type": "ticket.created",
        "subject": "Inbound Billing Issue",
        "description": "Customer needs invoice update.",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    now_ts = str(int(time.time()))

    headers = {
        "Content-Type": "application/json",
        "X-SupportGPT-Signature": _sign(raw_body, secret),
        "X-SupportGPT-Timestamp": now_ts,
    }

    res = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw_body, headers=headers
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "queued"
    assert data["duplicate"] is False
    assert "receipt_id" in data


@pytest.mark.asyncio
async def test_webhook_reception_invalid_signature_rejected(webhook_context):
    """Invalid signature returns 401 Unauthorized."""
    client, _, _, source, _ = webhook_context

    payload = {"event_id": "evt-002", "event_type": "ticket.created"}
    raw_body = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "X-SupportGPT-Signature": "sha256=invalidhex000000000000000000000000000000000000000000000000000000",
        "X-SupportGPT-Timestamp": str(int(time.time())),
    }

    res = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw_body, headers=headers
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "SIGNATURE_VERIFICATION_FAILED"


@pytest.mark.asyncio
async def test_webhook_reception_missing_signature_rejected(webhook_context):
    """Missing signature header returns 401 Unauthorized."""
    client, _, _, source, _ = webhook_context

    payload = {"event_id": "evt-003", "event_type": "ticket.created"}
    raw_body = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
    }

    res = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw_body, headers=headers
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "SIGNATURE_VERIFICATION_FAILED"


@pytest.mark.asyncio
async def test_webhook_reception_timestamp_expired_rejected(webhook_context):
    """Timestamp outside tolerance window returns 400 Bad Request."""
    client, _, _, source, secret = webhook_context

    payload = {"event_id": "evt-004", "event_type": "ticket.created"}
    raw_body = json.dumps(payload).encode("utf-8")
    expired_ts = str(int(time.time()) - 600)  # 10 minutes ago

    headers = {
        "Content-Type": "application/json",
        "X-SupportGPT-Signature": _sign(raw_body, secret),
        "X-SupportGPT-Timestamp": expired_ts,
    }

    res = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw_body, headers=headers
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "TIMESTAMP_OUTSIDE_TOLERANCE"


@pytest.mark.asyncio
async def test_webhook_reception_invalid_content_type_rejected(webhook_context):
    """Non-JSON content type returns 415 Unsupported Media Type."""
    client, _, _, source, secret = webhook_context

    raw_body = b"hello=world"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-SupportGPT-Signature": _sign(raw_body, secret),
        "X-SupportGPT-Timestamp": str(int(time.time())),
    }

    res = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw_body, headers=headers
    )
    assert res.status_code == 415
    assert res.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.asyncio
async def test_webhook_reception_idempotent_duplicate(webhook_context):
    """Identical event delivers idempotent 200 response with duplicate: true."""
    client, _, _, source, secret = webhook_context

    payload = {
        "event_id": "evt-dup-999",
        "event_type": "ticket.created",
        "subject": "Duplicate Test",
    }
    raw_body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-SupportGPT-Signature": _sign(raw_body, secret),
        "X-SupportGPT-Timestamp": str(int(time.time())),
    }

    # First delivery
    res1 = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw_body, headers=headers
    )
    assert res1.status_code == 202
    assert res1.json()["duplicate"] is False
    receipt_id = res1.json()["receipt_id"]

    # Duplicate delivery
    res2 = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw_body, headers=headers
    )
    assert res2.status_code == 200
    assert res2.json()["duplicate"] is True
    assert res2.json()["receipt_id"] == receipt_id


@pytest.mark.asyncio
async def test_webhook_reception_payload_mismatch_conflict(webhook_context):
    """Same event ID with differing payload returns 409 Conflict."""
    client, _, _, source, secret = webhook_context

    payload1 = {
        "event_id": "evt-conflict-001",
        "event_type": "ticket.created",
        "subject": "Version 1",
    }
    raw1 = json.dumps(payload1).encode("utf-8")
    headers1 = {
        "Content-Type": "application/json",
        "X-SupportGPT-Signature": _sign(raw1, secret),
        "X-SupportGPT-Timestamp": str(int(time.time())),
    }
    res1 = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw1, headers=headers1
    )
    assert res1.status_code == 202

    # Different payload with same event_id
    payload2 = {
        "event_id": "evt-conflict-001",
        "event_type": "ticket.created",
        "subject": "Version 2 TAMPERED",
    }
    raw2 = json.dumps(payload2).encode("utf-8")
    headers2 = {
        "Content-Type": "application/json",
        "X-SupportGPT-Signature": _sign(raw2, secret),
        "X-SupportGPT-Timestamp": str(int(time.time())),
    }
    res2 = await client.post(
        f"/api/v1/webhooks/sources/{source.id}", content=raw2, headers=headers2
    )
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "EVENT_PAYLOAD_MISMATCH"


@pytest.mark.asyncio
async def test_generic_webhook_routing_via_header(webhook_context):
    """POST /api/v1/webhooks/generic routes successfully via X-SupportGPT-Source-ID header."""
    client, _, _, source, secret = webhook_context

    payload = {
        "event_id": "evt-generic-123",
        "event_type": "ticket.created",
        "subject": "Generic Webhook",
    }
    raw = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-SupportGPT-Signature": _sign(raw, secret),
        "X-SupportGPT-Timestamp": str(int(time.time())),
        "X-SupportGPT-Source-ID": str(source.id),
    }

    res = await client.post("/api/v1/webhooks/generic", content=raw, headers=headers)
    assert res.status_code == 202
    assert res.json()["status"] == "queued"
