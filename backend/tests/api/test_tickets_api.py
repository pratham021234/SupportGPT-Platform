"""API tests for ticket management, filters, assignment, OCC, and lifecycle events."""

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
from app.models.enums import (
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
    UserStatus,
)
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
async def ticket_test_context() -> AsyncIterator[tuple[AsyncClient, AsyncSession, Organization, User, User]]:
    """Create test environment with organization, owner/agent user, and viewer user."""
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
        # 1. Organization
        org = Organization(name="Acme Support", slug="acme-support", status=OrganizationStatus.ACTIVE)
        db.add(org)
        await db.flush()

        # 2. Agent User (Caller)
        pwd_hash = hash_password("AgentPass123!Safe")
        agent_user = User(
            email="agent@acme.com",
            password_hash=pwd_hash,
            display_name="Agent Sarah",
            status=UserStatus.ACTIVE,
        )
        db.add(agent_user)
        await db.flush()

        # 3. Viewer User
        viewer_user = User(
            email="viewer@acme.com",
            password_hash=pwd_hash,
            display_name="Auditor Bob",
            status=UserStatus.ACTIVE,
        )
        db.add(viewer_user)
        await db.flush()

        # 4. Memberships
        agent_mem = OrganizationMembership(
            organization_id=org.id,
            user_id=agent_user.id,
            role=MembershipRole.AGENT,
            status=MembershipStatus.ACTIVE,
        )
        viewer_mem = OrganizationMembership(
            organization_id=org.id,
            user_id=viewer_user.id,
            role=MembershipRole.VIEWER,
            status=MembershipStatus.ACTIVE,
        )
        db.add_all([agent_mem, viewer_mem])
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        async with session_factory() as db:
            yield client, db, org, agent_user, viewer_user

    app.dependency_overrides.clear()
    await engine.dispose()


async def login_as(client: AsyncClient, email: str, password: str = "AgentPass123!Safe") -> None:
    """Helper to authenticate the test client."""
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_ticket_creation_and_defaults(ticket_test_context):
    """Verify ticket is created with sequential number, TICK-1 reference, default status and priority."""
    client, db, org, agent_user, _ = ticket_test_context
    await login_as(client, agent_user.email)

    payload = {
        "subject": "System login connectivity failure",
        "channel": "email",
    }
    res = await client.post(f"/api/v1/organizations/{org.id}/tickets", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["subject"] == "System login connectivity failure"
    assert data["status"] == "open"
    assert data["priority"] == "medium"
    assert data["ticket_number"] == 1
    assert data["ticket_reference"] == "TICK-1"
    assert data["lock_version"] == 1
    assert data["organization_id"] == str(org.id)


@pytest.mark.asyncio
async def test_ticket_creation_with_initial_description(ticket_test_context):
    """Verify description creates initial conversation and message atomically."""
    client, db, org, agent_user, _ = ticket_test_context
    await login_as(client, agent_user.email)

    payload = {
        "subject": "Hardware failure report",
        "description": "The server power supply exploded this morning.",
        "priority": "urgent",
    }
    res = await client.post(f"/api/v1/organizations/{org.id}/tickets", json=payload)
    assert res.status_code == 201
    ticket_id = res.json()["id"]

    # Verify conversation was created
    conv_res = await client.get(f"/api/v1/organizations/{org.id}/tickets/{ticket_id}/conversations")
    assert conv_res.status_code == 200
    conv_data = conv_res.json()["items"]
    assert len(conv_data) == 1
    conv_id = conv_data[0]["id"]

    # Verify initial message in thread
    msg_res = await client.get(f"/api/v1/organizations/{org.id}/conversations/{conv_id}/messages")
    assert msg_res.status_code == 200
    msg_data = msg_res.json()["items"]
    assert len(msg_data) == 1
    assert msg_data[0]["body_text"] == "The server power supply exploded this morning."
    assert msg_data[0]["author_type"] == "agent"


@pytest.mark.asyncio
async def test_ticket_creation_invalid_customer_rejected(ticket_test_context):
    """Verify referencing a nonexistent customer returns 404."""
    client, db, org, agent_user, _ = ticket_test_context
    await login_as(client, agent_user.email)

    random_cust_id = str(uuid.uuid4())
    payload = {
        "subject": "Missing customer ticket",
        "customer_id": random_cust_id,
    }
    res = await client.post(f"/api/v1/organizations/{org.id}/tickets", json=payload)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_ticket_listing_filters_and_pagination(ticket_test_context):
    """Verify ticket list supports status, priority, search, and pagination."""
    client, db, org, agent_user, _ = ticket_test_context
    await login_as(client, agent_user.email)

    # Seed 3 tickets
    await client.post(
        f"/api/v1/organizations/{org.id}/tickets",
        json={"subject": "Alpha issue", "priority": "low"},
    )
    await client.post(
        f"/api/v1/organizations/{org.id}/tickets",
        json={"subject": "Beta database crash", "priority": "urgent"},
    )
    await client.post(
        f"/api/v1/organizations/{org.id}/tickets",
        json={"subject": "Gamma issue", "priority": "high"},
    )

    # 1. Total count
    list_res = await client.get(f"/api/v1/organizations/{org.id}/tickets?limit=10")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 3

    # 2. Filter by priority
    urgent_res = await client.get(f"/api/v1/organizations/{org.id}/tickets?priority=urgent")
    assert urgent_res.status_code == 200
    assert urgent_res.json()["total"] == 1
    assert urgent_res.json()["items"][0]["subject"] == "Beta database crash"

    # 3. Search by keyword
    search_res = await client.get(f"/api/v1/organizations/{org.id}/tickets?search=database")
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1
    assert search_res.json()["items"][0]["subject"] == "Beta database crash"

    # 4. Pagination
    page_res = await client.get(f"/api/v1/organizations/{org.id}/tickets?limit=2&offset=0")
    assert page_res.status_code == 200
    assert len(page_res.json()["items"]) == 2


@pytest.mark.asyncio
async def test_ticket_status_transition_rules(ticket_test_context):
    """Verify valid transitions update ticket and invalid transitions return 409."""
    client, db, org, agent_user, _ = ticket_test_context
    await login_as(client, agent_user.email)

    create_res = await client.post(
        f"/api/v1/organizations/{org.id}/tickets",
        json={"subject": "Workflow check"},
    )
    ticket_id = create_res.json()["id"]

    # 1. Valid transition: open -> in_progress
    patch_res = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"status": "in_progress"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "in_progress"
    assert patch_res.json()["lock_version"] == 2

    # 2. Valid transition: in_progress -> resolved
    resolve_res = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"status": "resolved"},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "resolved"
    assert resolve_res.json()["resolved_at"] is not None

    # 3. Valid transition: resolved -> closed
    close_res = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"status": "closed"},
    )
    assert close_res.status_code == 200
    assert close_res.json()["status"] == "closed"
    assert close_res.json()["closed_at"] is not None

    # 4. Forbidden transition: closed -> in_progress (closed can only transition to open)
    invalid_res = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"status": "in_progress"},
    )
    assert invalid_res.status_code == 409
    assert invalid_res.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


@pytest.mark.asyncio
async def test_ticket_optimistic_concurrency_conflict(ticket_test_context):
    """Verify that submitting a stale lock_version returns 409 CONCURRENCY_CONFLICT."""
    client, db, org, agent_user, _ = ticket_test_context
    await login_as(client, agent_user.email)

    create_res = await client.post(
        f"/api/v1/organizations/{org.id}/tickets",
        json={"subject": "Concurrency test"},
    )
    ticket_id = create_res.json()["id"]
    assert create_res.json()["lock_version"] == 1

    # First update increments lock_version to 2
    update1 = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"priority": "high", "lock_version": 1},
    )
    assert update1.status_code == 200
    assert update1.json()["lock_version"] == 2

    # Second concurrent update using stale lock_version=1 must be rejected
    update2 = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"priority": "urgent", "lock_version": 1},
    )
    assert update2.status_code == 409
    assert update2.json()["error"]["code"] == "CONCURRENCY_CONFLICT"


@pytest.mark.asyncio
async def test_ticket_assignment_eligibility(ticket_test_context):
    """Verify assignment accepts agents and rejects read-only viewers or outsiders."""
    client, db, org, agent_user, viewer_user = ticket_test_context
    await login_as(client, agent_user.email)

    create_res = await client.post(
        f"/api/v1/organizations/{org.id}/tickets",
        json={"subject": "Assignment test"},
    )
    ticket_id = create_res.json()["id"]

    # 1. Assign to active agent -> SUCESS
    assign_agent = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"assigned_actor_id": str(agent_user.id)},
    )
    assert assign_agent.status_code == 200
    assert assign_agent.json()["assigned_actor_id"] == str(agent_user.id)

    # 2. Assign to active viewer -> REJECTED (viewers cannot be assigned tickets)
    assign_viewer = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"assigned_actor_id": str(viewer_user.id)},
    )
    assert assign_viewer.status_code == 409
    assert assign_viewer.json()["error"]["code"] == "INVALID_ASSIGNEE"

    # 3. Assign to random outsider -> REJECTED
    assign_outsider = await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"assigned_actor_id": str(uuid.uuid4())},
    )
    assert assign_outsider.status_code == 409
    assert assign_outsider.json()["error"]["code"] == "INVALID_ASSIGNEE"


@pytest.mark.asyncio
async def test_ticket_lifecycle_events_recorded(ticket_test_context):
    """Verify that ticket mutations produce append-only audit events and unchanged values do not duplicate."""
    client, db, org, agent_user, _ = ticket_test_context
    await login_as(client, agent_user.email)

    create_res = await client.post(
        f"/api/v1/organizations/{org.id}/tickets",
        json={"subject": "Event trail test", "priority": "low"},
    )
    ticket_id = create_res.json()["id"]

    # Mutation 1: Change priority to high
    await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"priority": "high"},
    )

    # Mutation 2: Change status to in_progress
    await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"status": "in_progress"},
    )

    # Non-mutation: submit identical status "in_progress" (should NOT produce event)
    await client.patch(
        f"/api/v1/organizations/{org.id}/tickets/{ticket_id}",
        json={"status": "in_progress"},
    )

    # Inspect events
    events_res = await client.get(f"/api/v1/organizations/{org.id}/tickets/{ticket_id}/events")
    assert events_res.status_code == 200
    events = events_res.json()["items"]

    # Expected events: created, priority_changed, status_changed
    event_types = [e["event_type"] for e in events]
    assert event_types == ["created", "priority_changed", "status_changed"]
    assert events[1]["previous_value"]["priority"] == "low"
    assert events[1]["new_value"]["priority"] == "high"
    assert events[2]["previous_value"]["status"] == "open"
    assert events[2]["new_value"]["status"] == "in_progress"
