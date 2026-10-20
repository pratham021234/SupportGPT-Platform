"""Security tests for multi-tenant isolation across drafts, verification runs, policies, approvals, and audit trails."""

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
async def multi_tenant_verification_context() -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], Organization, Organization, User, User]
]:
    """Test fixture with two isolated organizations: Alpha and Beta."""
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
        org_alpha = Organization(
            name="Alpha Corp", slug="alpha-corp", status=OrganizationStatus.ACTIVE.value
        )
        org_beta = Organization(
            name="Beta Corp", slug="beta-corp", status=OrganizationStatus.ACTIVE.value
        )
        db.add_all([org_alpha, org_beta])
        await db.flush()

        hashed_pw = hash_password("Secret123!Safe")

        user_alice = User(
            email="alice@alpha.com",
            display_name="Alice Alpha",
            password_hash=hashed_pw,
            status=UserStatus.ACTIVE.value,
        )
        user_bob = User(
            email="bob@beta.com",
            display_name="Bob Beta",
            password_hash=hashed_pw,
            status=UserStatus.ACTIVE.value,
        )
        db.add_all([user_alice, user_bob])
        await db.flush()

        mem_alice = OrganizationMembership(
            organization_id=org_alpha.id,
            user_id=user_alice.id,
            role=MembershipRole.OWNER.value,
            status=MembershipStatus.ACTIVE.value,
        )
        mem_bob = OrganizationMembership(
            organization_id=org_beta.id,
            user_id=user_bob.id,
            role=MembershipRole.OWNER.value,
            status=MembershipStatus.ACTIVE.value,
        )
        db.add_all([mem_alice, mem_bob])
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, session_factory, org_alpha, org_beta, user_alice, user_bob

    await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_draft_access_denied(multi_tenant_verification_context):
    """Verify that a user from Beta cannot read, revise, or access a draft created by Alpha."""
    client, session_factory, org_alpha, org_beta, user_alice, user_bob = (
        multi_tenant_verification_context
    )

    # 1. Login as Alice (Alpha) and create draft
    await client.post(
        "/api/v1/auth/login", json={"email": "alice@alpha.com", "password": "Secret123!Safe"}
    )
    alpha_draft_res = await client.post(
        f"/api/v1/organizations/{org_alpha.id}/drafts",
        json={
            "original_query": "Alpha query",
            "draft_text": "Confidential Alpha corporate guidance notes.",
            "evidence_references": [],
        },
    )
    assert alpha_draft_res.status_code == 201
    alpha_draft_id = alpha_draft_res.json()["id"]

    # 2. Login as Bob (Beta)
    await client.post(
        "/api/v1/auth/login", json={"email": "bob@beta.com", "password": "Secret123!Safe"}
    )

    # Attempt to read Alpha's draft using Beta's organization endpoint
    cross_read = await client.get(
        f"/api/v1/organizations/{org_beta.id}/drafts/{alpha_draft_id}",
    )
    # MUST return 404 Not Found (draft does not exist in Beta)
    assert cross_read.status_code == 404

    # Attempt to revise Alpha's draft through Beta
    cross_revise = await client.put(
        f"/api/v1/organizations/{org_beta.id}/drafts/{alpha_draft_id}",
        json={"draft_text": "Hacked draft content"},
    )
    assert cross_revise.status_code == 404

    # Attempt direct-ID access under Alpha's path
    cross_route = await client.get(
        f"/api/v1/organizations/{org_alpha.id}/drafts/{alpha_draft_id}",
    )
    # MUST return 403 Forbidden (Bob is not a member of Alpha)
    assert cross_route.status_code == 403


@pytest.mark.asyncio
async def test_cross_tenant_verification_and_approval_isolation(multi_tenant_verification_context):
    """Verify that verification runs, approvals, and policies are strictly isolated between tenants."""
    client, session_factory, org_alpha, org_beta, user_alice, user_bob = (
        multi_tenant_verification_context
    )

    # 1. Alice (Alpha) creates draft, runs verification, and requests approval
    await client.post(
        "/api/v1/auth/login", json={"email": "alice@alpha.com", "password": "Secret123!Safe"}
    )
    draft_res = await client.post(
        f"/api/v1/organizations/{org_alpha.id}/drafts",
        json={
            "original_query": "Policy question",
            "draft_text": "Alpha policy text.",
            "evidence_references": [],
        },
    )
    draft_id = draft_res.json()["id"]

    verify_res = await client.post(f"/api/v1/organizations/{org_alpha.id}/drafts/{draft_id}/verify")
    run_id = verify_res.json()["id"]

    appr_res = await client.post(
        f"/api/v1/organizations/{org_alpha.id}/drafts/{draft_id}/approvals",
        json={
            "draft_version": 1,
            "verification_run_id": run_id,
            "required_role": "agent",
            "separation_of_duties": False,
        },
    )
    approval_id = appr_res.json()["id"]

    # Alice also creates a policy in Alpha
    await client.post(
        f"/api/v1/organizations/{org_alpha.id}/policies",
        json={
            "name": "Alpha Strict Grounding",
            "policy_category": "factual_grounding",
            "severity": "high",
            "rule_type": "unsupported_claim_block",
            "rule_config": {},
        },
    )

    # 2. Login as Bob (Beta)
    await client.post(
        "/api/v1/auth/login", json={"email": "bob@beta.com", "password": "Secret123!Safe"}
    )

    # Attempt to access Alice's verification runs through Beta
    cross_run = await client.get(
        f"/api/v1/organizations/{org_beta.id}/drafts/{draft_id}/verification-runs"
    )
    # Returns 0 runs (draft does not exist in Beta)
    assert cross_run.status_code == 200
    assert cross_run.json()["total"] == 0

    # Attempt to decide Alice's approval request through Beta
    cross_decision = await client.post(
        f"/api/v1/organizations/{org_beta.id}/approvals/{approval_id}/decision",
        json={"decision": "approve", "reason": "Cross-tenant unauthorized approve"},
    )
    assert cross_decision.status_code == 404

    # List Beta's policies -> should NOT contain Alpha's policy
    beta_policies = await client.get(f"/api/v1/organizations/{org_beta.id}/policies")
    assert beta_policies.status_code == 200
    assert beta_policies.json()["total"] == 0

    # Query Beta's audit log -> should contain 0 events from Alpha
    beta_audit = await client.get(f"/api/v1/organizations/{org_beta.id}/verification-audit")
    assert beta_audit.status_code == 200
    assert beta_audit.json()["total"] == 0
