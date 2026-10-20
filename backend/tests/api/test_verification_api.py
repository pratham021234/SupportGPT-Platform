"""API integration tests for Response Verification, Policy Enforcement, and Human Approvals."""

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
async def verification_api_context() -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], Organization, User, User, User]
]:
    """Test fixture with an active organization, owner, admin, and agent users."""
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
        org = Organization(
            name="SaaS Corp", slug="saas-corp", status=OrganizationStatus.ACTIVE.value
        )
        db.add(org)
        await db.flush()

        hashed_pw = hash_password("Pass123!Safe")

        # Owner: Alice
        alice = User(
            email="alice@saas.com",
            display_name="Alice Owner",
            password_hash=hashed_pw,
            status=UserStatus.ACTIVE.value,
        )
        # Agent: Bob
        bob = User(
            email="bob@saas.com",
            display_name="Bob Agent",
            password_hash=hashed_pw,
            status=UserStatus.ACTIVE.value,
        )
        # Admin: Charlie
        charlie = User(
            email="charlie@saas.com",
            display_name="Charlie Admin",
            password_hash=hashed_pw,
            status=UserStatus.ACTIVE.value,
        )

        db.add_all([alice, bob, charlie])
        await db.flush()

        mem_alice = OrganizationMembership(
            organization_id=org.id,
            user_id=alice.id,
            role=MembershipRole.OWNER.value,
            status=MembershipStatus.ACTIVE.value,
        )
        mem_bob = OrganizationMembership(
            organization_id=org.id,
            user_id=bob.id,
            role=MembershipRole.AGENT.value,
            status=MembershipStatus.ACTIVE.value,
        )
        mem_charlie = OrganizationMembership(
            organization_id=org.id,
            user_id=charlie.id,
            role=MembershipRole.ADMIN.value,
            status=MembershipStatus.ACTIVE.value,
        )
        db.add_all([mem_alice, mem_bob, mem_charlie])
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, session_factory, org, alice, bob, charlie

    await engine.dispose()


@pytest.mark.asyncio
async def test_response_draft_verification_and_approval_lifecycle(verification_api_context):
    """End-to-end verification lifecycle: create draft, verify, request approval, approve, revise, invalidate."""
    client, session_factory, org, alice, bob, charlie = verification_api_context

    # 1. Login as Bob (Agent)
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@saas.com", "password": "Pass123!Safe"},
    )
    assert login_res.status_code == 200

    # 2. Create Response Draft
    create_draft_res = await client.post(
        f"/api/v1/organizations/{org.id}/drafts",
        json={
            "original_query": "What are your password requirements?",
            "draft_text": "Passwords must be at least 16 characters in length according to security standards.",
            "evidence_references": [
                {
                    "chunk_id": str(uuid.uuid4()),
                    "excerpt": "According to enterprise security standards, passwords must be at least 16 characters in length.",
                    "source_title": "Security Handbook",
                }
            ],
        },
    )
    assert create_draft_res.status_code == 201
    draft_data = create_draft_res.json()
    draft_id = draft_data["id"]
    assert draft_data["version_number"] == 1
    assert draft_data["lifecycle_status"] == "draft"

    # 3. Execute Verification Pipeline
    verify_res = await client.post(
        f"/api/v1/organizations/{org.id}/drafts/{draft_id}/verify",
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    run_id = verify_data["id"]
    assert verify_data["status"] == "passed"
    assert verify_data["risk_level"] == "low"
    assert len(verify_data["claim_findings"]) >= 1
    assert verify_data["claim_findings"][0]["support_status"] == "supported"

    # 4. Submit for Approval
    approval_req_res = await client.post(
        f"/api/v1/organizations/{org.id}/drafts/{draft_id}/approvals",
        json={
            "draft_version": 1,
            "verification_run_id": run_id,
            "required_role": "agent",
            "separation_of_duties": True,
        },
    )
    assert approval_req_res.status_code == 201
    approval_data = approval_req_res.json()
    approval_id = approval_data["id"]
    assert approval_data["status"] == "pending"

    # 5. Attempt Self-Approval as Bob (Agent) -> MUST return 403 Forbidden
    self_approve_res = await client.post(
        f"/api/v1/organizations/{org.id}/approvals/{approval_id}/decision",
        json={"decision": "approve", "reason": "Self-approving"},
    )
    assert self_approve_res.status_code == 403
    assert self_approve_res.json()["error"]["code"] == "SELF_APPROVAL_FORBIDDEN"

    # 6. Login as Charlie (Admin)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "charlie@saas.com", "password": "Pass123!Safe"},
    )

    # 7. Independent Approval by Charlie
    approve_res = await client.post(
        f"/api/v1/organizations/{org.id}/approvals/{approval_id}/decision",
        json={"decision": "approve", "reason": "Verified accurate against security handbook."},
    )
    assert approve_res.status_code == 200
    approved_data = approve_res.json()
    assert approved_data["status"] == "approved"
    assert approved_data["decision_by_user_id"] == str(charlie.id)

    # 8. Login back as Bob (Agent) and revise the draft
    await client.post(
        "/api/v1/auth/login",
        json={"email": "bob@saas.com", "password": "Pass123!Safe"},
    )

    revise_res = await client.put(
        f"/api/v1/organizations/{org.id}/drafts/{draft_id}",
        json={
            "draft_text": "Updated text: passwords must be 16 characters and contain a special symbol."
        },
    )
    assert revise_res.status_code == 200
    revised_data = revise_res.json()
    assert revised_data["version_number"] == 2
    assert revised_data["lifecycle_status"] == "draft"

    # 9. Verify prior approval for version 1 was automatically invalidated
    get_old_appr = await client.get(
        f"/api/v1/organizations/{org.id}/approvals/{approval_id}",
    )
    assert get_old_appr.status_code == 200
    assert get_old_appr.json()["status"] == "invalidated"

    # 10. Query Audit Trail
    audit_res = await client.get(
        f"/api/v1/organizations/{org.id}/verification-audit",
    )
    assert audit_res.status_code == 200
    audit_events = audit_res.json()["items"]
    event_types = [e["event_type"] for e in audit_events]
    assert "draft_created" in event_types
    assert "verification_completed" in event_types
    assert "approval_requested" in event_types
    assert "approval_granted" in event_types
    assert "draft_revised" in event_types
    assert "approval_invalidated" in event_types


@pytest.mark.asyncio
async def test_policy_management_and_rejection_workflow(verification_api_context):
    """Verify policy management and rejection / revision request workflow."""
    client, session_factory, org, alice, bob, charlie = verification_api_context

    # 1. Login as Charlie (Admin)
    await client.post(
        "/api/v1/auth/login",
        json={"email": "charlie@saas.com", "password": "Pass123!Safe"},
    )

    # 2. Create custom prohibited terms policy
    create_policy_res = await client.post(
        f"/api/v1/organizations/{org.id}/policies",
        json={
            "name": "No Guarantees Policy",
            "description": "Prevents unauthorized guarantees",
            "policy_category": "prohibited_terms",
            "severity": "high",
            "rule_type": "keyword_prohibition",
            "rule_config": {
                "prohibited_terms": ["100% guaranteed", "free forever"],
                "case_sensitive": False,
            },
            "is_enabled": True,
        },
    )
    assert create_policy_res.status_code == 201
    policy_id = create_policy_res.json()["id"]

    # 3. Toggle policy off and on
    toggle_res = await client.patch(
        f"/api/v1/organizations/{org.id}/policies/{policy_id}/toggle",
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_enabled"] is False

    toggle_on = await client.patch(
        f"/api/v1/organizations/{org.id}/policies/{policy_id}/toggle",
    )
    assert toggle_on.status_code == 200
    assert toggle_on.json()["is_enabled"] is True

    # 4. Create draft violating the prohibited terms policy
    draft_res = await client.post(
        f"/api/v1/organizations/{org.id}/drafts",
        json={
            "original_query": "Is your service guaranteed?",
            "draft_text": "Yes, our service is 100% guaranteed to never experience downtime.",
            "evidence_references": [],
        },
    )
    assert draft_res.status_code == 201
    draft_id = draft_res.json()["id"]

    # 5. Verify draft -> should flag policy violation
    verify_res = await client.post(
        f"/api/v1/organizations/{org.id}/drafts/{draft_id}/verify",
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["status"] in ["needs_revision", "blocked"]
    assert verify_data["risk_level"] in ["high", "critical"]

    # 6. Request approval
    appr_res = await client.post(
        f"/api/v1/organizations/{org.id}/drafts/{draft_id}/approvals",
        json={
            "draft_version": 1,
            "verification_run_id": verify_data["id"],
            "required_role": "admin",
            "separation_of_duties": False,
        },
    )
    appr_id = appr_res.json()["id"]

    # 7. Reject with explicit reason
    reject_res = await client.post(
        f"/api/v1/organizations/{org.id}/approvals/{appr_id}/decision",
        json={
            "decision": "reject",
            "reason": "Draft promises 100% uptime guarantee violating company policy.",
        },
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"
    assert "100% uptime guarantee" in reject_res.json()["decision_reason"]
