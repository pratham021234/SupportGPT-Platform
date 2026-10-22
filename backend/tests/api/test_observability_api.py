"""API integration tests for AI Observability, Traces, Investigations, Evaluations, and Usage."""

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
    AIOperationType,
    FailureCategory,
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
    UserStatus,
)
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User
from app.services.observability.investigation_service import InvestigationService
from app.services.observability.tracer import AITracer
from app.services.observability.usage_service import UsageAccountingService


@pytest.fixture
async def observability_api_context() -> AsyncIterator[
    tuple[AsyncClient, async_sessionmaker[AsyncSession], Organization, User]
]:
    """Test fixture with an active organization and admin user."""
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
            name="Reliability Labs", slug="reliability-labs", status=OrganizationStatus.ACTIVE.value
        )
        db.add(org)
        await db.flush()

        hashed_pw = hash_password("Pass123!Safe")
        admin = User(
            email="admin@reliability.com",
            display_name="Alice Admin",
            password_hash=hashed_pw,
            status=UserStatus.ACTIVE.value,
        )
        db.add(admin)
        await db.flush()

        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=admin.id,
            role=MembershipRole.ADMIN.value,
            status=MembershipStatus.ACTIVE.value,
        )
        db.add(membership)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@reliability.com", "password": "Pass123!Safe"},
        )
        assert login_res.status_code == 200
        yield client, session_factory, org, admin
    await engine.dispose()


@pytest.mark.asyncio
async def test_diagnostics_endpoint(observability_api_context) -> None:
    client, _, org, _ = observability_api_context

    res = await client.get(f"/api/v1/organizations/{org.id}/observability/diagnostics")
    assert res.status_code == 200
    data = res.json()
    assert "dependencies" in data
    assert "workers" in data
    assert "ai_providers" in data
    assert "status" in data


@pytest.mark.asyncio
async def test_traces_and_usage_lifecycle(observability_api_context) -> None:
    client, session_factory, org, admin = observability_api_context

    # 1. Create a simulated execution trace with spans
    async with session_factory() as session:
        async with AITracer.start_trace(
            session=session,
            organization_id=org.id,
            operation_type=AIOperationType.RAG_QUERY.value,
            provider="fastembed",
            model="bge-small-en-v1.5",
            user_id=admin.id,
        ) as trace:
            async with trace.span("query_embedding"):
                pass
            async with trace.span("vector_retrieval"):
                pass
            trace.evidence_count = 3
            trace.set_tokens(
                input_tokens=150, output_tokens=0, embedding_tokens=150, estimated_cost_usd=0.0
            )

        # Record usage
        await UsageAccountingService.record_usage(
            session=session,
            organization_id=org.id,
            operation_type=AIOperationType.RAG_QUERY.value,
            provider="fastembed",
            model="bge-small-en-v1.5",
            embedding_tokens=150,
            trace_id=trace.trace_id,
        )
        await session.commit()

    trace_id = trace.trace_id

    # 2. List traces
    list_res = await client.get(f"/api/v1/organizations/{org.id}/observability/traces")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(t["trace_id"] == trace_id for t in list_data["items"])

    # 3. Retrieve trace detail
    detail_res = await client.get(f"/api/v1/organizations/{org.id}/observability/traces/{trace_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["trace_id"] == trace_id
    assert len(detail_data["spans"]) == 2
    assert detail_data["spans"][0]["stage"] == "query_embedding"
    assert detail_data["spans"][1]["stage"] == "vector_retrieval"

    # 4. Inspect Usage Summary
    usage_res = await client.get(f"/api/v1/organizations/{org.id}/observability/usage")
    assert usage_res.status_code == 200
    usage_data = usage_res.json()
    assert usage_data["total_tokens"] == 150
    assert len(usage_data["by_model"]) >= 1


@pytest.mark.asyncio
async def test_failure_investigations_lifecycle(observability_api_context) -> None:
    client, session_factory, org, _ = observability_api_context

    # 1. Record an operational failure
    async with session_factory() as session:
        inv = await InvestigationService.record_failure(
            session=session,
            organization_id=org.id,
            error="No relevant evidence found in collection 'security_policies'",
            category=FailureCategory.NO_RELEVANT_EVIDENCE.value,
            severity="medium",
        )
        await session.commit()
        inv_id = inv.investigation_id

    # 2. List investigations
    list_res = await client.get(f"/api/v1/organizations/{org.id}/observability/investigations")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(i["investigation_id"] == inv_id for i in list_data["items"])

    # 3. Retrieve investigation detail
    detail_res = await client.get(
        f"/api/v1/organizations/{org.id}/observability/investigations/{inv_id}"
    )
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["investigation_id"] == inv_id
    assert detail_data["status"] == "open"
    assert len(detail_data["diagnostic_hypotheses"]) >= 1

    # 4. Update investigation status and notes
    patch_res = await client.patch(
        f"/api/v1/organizations/{org.id}/observability/investigations/{inv_id}",
        json={
            "status": "investigating",
            "resolution_notes": "Indexed new document version v2 to supply missing policy evidence.",
        },
    )
    assert patch_res.status_code == 200
    patched_data = patch_res.json()
    assert patched_data["status"] == "investigating"
    assert "v2" in patched_data["resolution_notes"]


@pytest.mark.asyncio
async def test_evaluations_run_and_compare(observability_api_context) -> None:
    client, _, org, _ = observability_api_context

    # 1. Trigger benchmark run 1
    run1_res = await client.post(f"/api/v1/organizations/{org.id}/observability/evaluations/run")
    assert run1_res.status_code == 201
    run1_data = run1_res.json()
    run1_id = run1_data["id"]
    assert run1_data["total_cases"] >= 5
    assert run1_data["status"] == "completed"
    assert run1_data["mean_recall_at_k"] >= 0.0

    # 2. Trigger benchmark run 2
    run2_res = await client.post(f"/api/v1/organizations/{org.id}/observability/evaluations/run")
    assert run2_res.status_code == 201
    run2_data = run2_res.json()
    run2_id = run2_data["id"]

    # 3. Compare run 1 vs run 2
    compare_res = await client.get(
        f"/api/v1/organizations/{org.id}/observability/evaluations/compare",
        params={"baseline_id": run1_id, "candidate_id": run2_id},
    )
    assert compare_res.status_code == 200
    compare_data = compare_res.json()
    assert compare_data["baseline_id"] == run1_id
    assert compare_data["candidate_id"] == run2_id
    assert "comparison" in compare_data
    assert "is_regression" in compare_data
