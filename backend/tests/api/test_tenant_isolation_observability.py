"""Security tests verifying strict tenant isolation across Observability endpoints."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_application
from app.models.ai_operation_trace import AIOperationTrace
from app.models.ai_token_usage import AITokenUsageRecord
from app.models.enums import (
    AIOperationType,
    EvaluationStatus,
    FailureCategory,
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
    TraceOutcome,
    UserStatus,
)
from app.models.evaluation_run import EvaluationRunRecord
from app.models.failure_investigation import FailureInvestigation
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User


@pytest.fixture
async def multi_tenant_obs_context() -> AsyncIterator[
    tuple[AsyncClient, Organization, Organization, User]
]:
    """Test fixture with two distinct organizations (Tenant A and Tenant B) and an admin of Tenant A."""
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
        # Tenant A
        org_a = Organization(
            name="Tenant Alpha", slug="tenant-alpha", status=OrganizationStatus.ACTIVE.value
        )
        # Tenant B
        org_b = Organization(
            name="Tenant Beta", slug="tenant-beta", status=OrganizationStatus.ACTIVE.value
        )
        db.add_all([org_a, org_b])
        await db.flush()

        hashed_pw = hash_password("Pass123!Safe")
        user_a = User(
            email="admin@alpha.com",
            display_name="Alpha Admin",
            password_hash=hashed_pw,
            status=UserStatus.ACTIVE.value,
        )
        db.add(user_a)
        await db.flush()

        membership_a = OrganizationMembership(
            organization_id=org_a.id,
            user_id=user_a.id,
            role=MembershipRole.ADMIN.value,
            status=MembershipStatus.ACTIVE.value,
        )
        db.add(membership_a)

        now = datetime.now(UTC)

        # Seed Tenant B Trace
        trace_b = AIOperationTrace(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            trace_id="trace_beta_secret_999",
            operation_type=AIOperationType.RAG_QUERY.value,
            provider="openai",
            model="gpt-4o",
            start_time=now,
            end_time=now,
            duration_ms=45.2,
            outcome=TraceOutcome.SUCCESS.value,
            token_usage={"total_tokens": 500},
            created_at=now,
        )
        db.add(trace_b)

        # Seed Tenant B Failure Investigation
        inv_b = FailureInvestigation(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            investigation_id="INV-BETA-01",
            fingerprint="fingerprint_beta_123",
            failure_category=FailureCategory.POLICY_VIOLATION.value,
            sanitized_error_summary="Confidential Tenant B compliance violation",
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(inv_b)

        # Seed Tenant B Evaluation Run
        eval_b = EvaluationRunRecord(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            dataset_id="beta_private_eval",
            dataset_version="v2.0",
            embedding_provider="fastembed",
            embedding_model="bge-small-en-v1.5",
            mean_recall_at_k=0.88,
            mean_reciprocal_rank=0.85,
            citation_validity_rate=0.95,
            abstention_accuracy=1.0,
            status=EvaluationStatus.COMPLETED.value,
            created_at=now,
        )
        db.add(eval_b)

        # Seed Tenant B Token Usage
        usage_b = AITokenUsageRecord(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            operation_type="private_op",
            provider="openai",
            model="gpt-4o",
            input_tokens=100000,
            output_tokens=20000,
            total_tokens=120000,
            estimated_cost_usd=0.45,
            created_at=now,
        )
        db.add(usage_b)

        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@alpha.com", "password": "Pass123!Safe"},
        )
        assert login_res.status_code == 200
        yield client, org_a, org_b, user_a
    await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_trace_access_denied(multi_tenant_obs_context) -> None:
    client, org_a, org_b, _ = multi_tenant_obs_context

    # 1. Attempt to view Tenant B's trace via Tenant A's route
    res1 = await client.get(
        f"/api/v1/organizations/{org_a.id}/observability/traces/trace_beta_secret_999"
    )
    assert res1.status_code == 404

    # 2. Attempt direct route hijacking on Tenant B's organization ID
    res2 = await client.get(
        f"/api/v1/organizations/{org_b.id}/observability/traces/trace_beta_secret_999"
    )
    assert res2.status_code in (
        403,
        404,
    )  # 403 Forbidden because caller is not a member of Tenant B


@pytest.mark.asyncio
async def test_cross_tenant_investigation_access_denied(multi_tenant_obs_context) -> None:
    client, org_a, org_b, _ = multi_tenant_obs_context

    # Attempt to read Tenant B investigation via Tenant A route
    res1 = await client.get(
        f"/api/v1/organizations/{org_a.id}/observability/investigations/INV-BETA-01"
    )
    assert res1.status_code == 404

    # Attempt to update Tenant B investigation via Tenant A route
    res2 = await client.patch(
        f"/api/v1/organizations/{org_a.id}/observability/investigations/INV-BETA-01",
        json={"status": "resolved"},
    )
    assert res2.status_code == 404

    # Attempt direct route hijacking on Tenant B's route
    res3 = await client.get(
        f"/api/v1/organizations/{org_b.id}/observability/investigations/INV-BETA-01"
    )
    assert res3.status_code in (403, 404)


@pytest.mark.asyncio
async def test_cross_tenant_usage_data_isolation(multi_tenant_obs_context) -> None:
    client, org_a, _, _ = multi_tenant_obs_context

    # Tenant A views its usage summary - must be 0 and have zero Tenant B records
    res = await client.get(f"/api/v1/organizations/{org_a.id}/observability/usage")
    assert res.status_code == 200
    data = res.json()
    assert data["total_tokens"] == 0
    assert data["total_estimated_cost_usd"] == 0.0
    assert len(data["by_model"]) == 0
