"""Integration tests running AI Observability, Traces, Investigations, and Evaluations against live PostgreSQL 16 with RLS."""

import os
import uuid

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.ai_operation_trace import AIOperationTrace
from app.models.ai_token_usage import AITokenUsageRecord
from app.models.enums import (
    AIOperationType,
    FailureCategory,
    OrganizationStatus,
    UserStatus,
)
from app.models.evaluation_run import EvaluationRunRecord
from app.models.failure_investigation import FailureInvestigation
from app.models.organization import Organization
from app.models.user import User
from app.services.observability.evaluation_service import EvaluationService
from app.services.observability.investigation_service import InvestigationService
from app.services.observability.tracer import AITracer
from app.services.observability.usage_service import UsageAccountingService

POSTGRES_TEST_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://supportgpt_user:supportgpt_dev_password@localhost:5432/supportgpt_test_db",
)


@pytest.fixture
async def live_postgres_obs_env():
    """Fixture providing a live PostgreSQL connection and clean test organization."""
    engine = create_async_engine(POSTGRES_TEST_URL, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Live PostgreSQL not reachable at {POSTGRES_TEST_URL}: {exc}")

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async with session_factory() as session:
        # Enable admin bypass to seed test organization and user
        await session.execute(text("SELECT set_config('app.is_system_admin', 'true', false)"))
        org = Organization(
            id=org_id,
            name="Live Observability Org",
            slug=f"live-obs-{org_id.hex[:6]}",
            status=OrganizationStatus.ACTIVE.value,
        )
        session.add(org)

        user = User(
            id=user_id,
            email=f"obs-{user_id.hex[:6]}@live.com",
            display_name="Live Obs User",
            password_hash="argon2id$test_hash",
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.commit()

    try:
        yield session_factory, org_id, user_id
    finally:
        async with session_factory() as session:
            await session.execute(text("SELECT set_config('app.is_system_admin', 'true', false)"))
            await session.execute(
                delete(AITokenUsageRecord).where(AITokenUsageRecord.organization_id == org_id)
            )
            await session.execute(
                delete(EvaluationRunRecord).where(EvaluationRunRecord.organization_id == org_id)
            )
            await session.execute(
                delete(FailureInvestigation).where(FailureInvestigation.organization_id == org_id)
            )
            await session.execute(
                delete(AIOperationTrace).where(AIOperationTrace.organization_id == org_id)
            )
            await session.execute(delete(User).where(User.id == user_id))
            await session.execute(delete(Organization).where(Organization.id == org_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_live_postgres_observability_pipeline(live_postgres_obs_env) -> None:
    session_factory, org_id, user_id = live_postgres_obs_env

    async with session_factory() as session:
        # 1. Enforce tenant RLS context
        await session.execute(text("SELECT set_config('app.is_system_admin', 'false', false)"))
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": str(org_id)},
        )

        # 2. Execute and persist AI execution trace with spans
        async with AITracer.start_trace(
            session=session,
            organization_id=org_id,
            operation_type=AIOperationType.ANSWER_GENERATION.value,
            provider="fastembed",
            model="bge-small-en-v1.5",
            user_id=user_id,
        ) as trace:
            async with trace.span("evidence_retrieval"):
                pass
            async with trace.span("grounded_generation"):
                pass
            trace.evidence_count = 5
            trace.set_tokens(
                input_tokens=200, output_tokens=50, embedding_tokens=200, estimated_cost_usd=0.001
            )

        trace_id = trace.trace_id

        # 3. Record and deduplicate failure investigation
        inv1 = await InvestigationService.record_failure(
            session=session,
            organization_id=org_id,
            error="PostgreSQL query latency spike in knowledge search",
            category=FailureCategory.DATABASE_FAILURE.value,
            severity="high",
            trace_id=trace_id,
        )
        assert inv1.occurrence_count == 1

        # Duplicate failure must increment occurrence count
        inv2 = await InvestigationService.record_failure(
            session=session,
            organization_id=org_id,
            error="PostgreSQL query latency spike in knowledge search",
            category=FailureCategory.DATABASE_FAILURE.value,
            severity="high",
            trace_id=trace_id,
        )
        assert inv2.id == inv1.id
        assert inv2.occurrence_count == 2

        # 4. Record token usage
        await UsageAccountingService.record_usage(
            session=session,
            organization_id=org_id,
            operation_type=AIOperationType.ANSWER_GENERATION.value,
            provider="openai",
            model="gpt-4o",
            input_tokens=200,
            output_tokens=50,
            trace_id=trace_id,
        )

        # 5. Execute benchmark evaluation and persist run
        eval_run = await EvaluationService.run_benchmark(
            session=session,
            organization_id=org_id,
            user_id=user_id,
        )
        assert eval_run.id is not None
        assert eval_run.mean_recall_at_k >= 0.0

        await session.commit()

    # 6. Verify PostgreSQL Row-Level Security (RLS) enforcement
    async with session_factory() as session:
        # Under Tenant A context: records visible
        await session.execute(text("SELECT set_config('app.is_system_admin', 'false', false)"))
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": str(org_id)},
        )

        traces_q = await session.execute(select(AIOperationTrace))
        assert len(traces_q.scalars().all()) == 1

        inv_q = await session.execute(select(FailureInvestigation))
        assert len(inv_q.scalars().all()) == 1

        eval_q = await session.execute(select(EvaluationRunRecord))
        assert len(eval_q.scalars().all()) == 1

        usage_q = await session.execute(select(AITokenUsageRecord))
        assert len(usage_q.scalars().all()) == 1

        # Switch context to an unauthorized different organization ID
        other_org_id = uuid.uuid4()
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": str(other_org_id)},
        )

        # RLS must completely filter all Tenant A records, yielding 0 rows
        cross_traces = (await session.execute(select(AIOperationTrace))).scalars().all()
        assert len(cross_traces) == 0

        cross_invs = (await session.execute(select(FailureInvestigation))).scalars().all()
        assert len(cross_invs) == 0

        cross_evals = (await session.execute(select(EvaluationRunRecord))).scalars().all()
        assert len(cross_evals) == 0

        cross_usages = (await session.execute(select(AITokenUsageRecord))).scalars().all()
        assert len(cross_usages) == 0
