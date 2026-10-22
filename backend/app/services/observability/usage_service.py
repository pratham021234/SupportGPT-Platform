"""Usage Accounting Service for token tracking, cost estimation, and audit summaries."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.ai_token_usage import AITokenUsageRecord

logger = get_logger("supportgpt.observability.usage")

# Documented pricing rates per 1,000,000 tokens (in USD)
# Source: Official provider published rates (Q1 2026 effective catalog)
MODEL_PRICING_CATALOG: dict[str, dict[str, Any]] = {
    "openai/gpt-4o": {
        "input_rate_per_1m": 2.50,
        "output_rate_per_1m": 10.00,
        "embedding_rate_per_1m": 0.00,
        "tier": "openai-2026-q1",
    },
    "openai/gpt-4o-mini": {
        "input_rate_per_1m": 0.15,
        "output_rate_per_1m": 0.60,
        "embedding_rate_per_1m": 0.00,
        "tier": "openai-2026-q1",
    },
    "openai/text-embedding-3-small": {
        "input_rate_per_1m": 0.02,
        "output_rate_per_1m": 0.00,
        "embedding_rate_per_1m": 0.02,
        "tier": "openai-2026-q1",
    },
    "fastembed/BAAI/bge-small-en-v1.5": {
        "input_rate_per_1m": 0.00,
        "output_rate_per_1m": 0.00,
        "embedding_rate_per_1m": 0.00,
        "tier": "local-onnx-free",
    },
    "deterministic/rules": {
        "input_rate_per_1m": 0.00,
        "output_rate_per_1m": 0.00,
        "embedding_rate_per_1m": 0.00,
        "tier": "system-free",
    },
}


class UsageAccountingService:
    """Calculates token costs and persists usage records with tenant attribution."""

    @staticmethod
    def calculate_cost(
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        embedding_tokens: int = 0,
    ) -> tuple[float, str]:
        """Calculate estimated cost in USD based on published model rates."""
        lookup_key = f"{provider.lower()}/{model}"
        rates = MODEL_PRICING_CATALOG.get(lookup_key)

        if not rates:
            # Fallback for local models
            if "fastembed" in provider.lower() or "local" in provider.lower():
                return 0.0, "local-onnx-free"
            # Generic estimate for unknown cloud models
            rates = {
                "input_rate_per_1m": 1.00,
                "output_rate_per_1m": 3.00,
                "embedding_rate_per_1m": 0.10,
                "tier": "estimated-fallback",
            }

        input_cost = (input_tokens / 1_000_000.0) * rates["input_rate_per_1m"]
        output_cost = (output_tokens / 1_000_000.0) * rates["output_rate_per_1m"]
        embed_cost = (embedding_tokens / 1_000_000.0) * rates["embedding_rate_per_1m"]

        total_cost = round(input_cost + output_cost + embed_cost, 6)
        return total_cost, rates["tier"]

    @classmethod
    async def record_usage(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        operation_type: str,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        embedding_tokens: int = 0,
        is_provider_reported: bool = False,
        trace_id: str | None = None,
    ) -> AITokenUsageRecord:
        """Persist a token usage record and estimated cost."""
        estimated_cost, tier = cls.calculate_cost(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            embedding_tokens=embedding_tokens,
        )

        total_tokens = input_tokens + output_tokens + embedding_tokens

        record = AITokenUsageRecord(
            id=uuid.uuid4(),
            organization_id=organization_id,
            trace_id=trace_id,
            operation_type=operation_type,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            embedding_tokens=embedding_tokens,
            total_tokens=total_tokens,
            is_provider_reported=is_provider_reported,
            estimated_cost_usd=estimated_cost,
            pricing_tier=tier,
            created_at=datetime.now(UTC),
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def get_usage_summary(
        session: AsyncSession,
        organization_id: uuid.UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Generate tenant usage breakdown by model and operation."""
        query = select(AITokenUsageRecord).where(
            AITokenUsageRecord.organization_id == organization_id
        )

        if start_date:
            query = query.where(AITokenUsageRecord.created_at >= start_date)
        if end_date:
            query = query.where(AITokenUsageRecord.created_at <= end_date)

        result = await session.execute(query.order_by(desc(AITokenUsageRecord.created_at)))
        records = list(result.scalars().all())

        total_input_tokens = sum(r.input_tokens for r in records)
        total_output_tokens = sum(r.output_tokens for r in records)
        total_embedding_tokens = sum(r.embedding_tokens for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        total_estimated_cost = sum(r.estimated_cost_usd for r in records)

        by_model: dict[str, dict[str, Any]] = {}
        by_operation: dict[str, dict[str, Any]] = {}

        for r in records:
            # Model grouping
            model_key = f"{r.provider}/{r.model}"
            if model_key not in by_model:
                by_model[model_key] = {
                    "provider": r.provider,
                    "model": r.model,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "request_count": 0,
                    "is_provider_reported": r.is_provider_reported,
                }
            by_model[model_key]["total_tokens"] += r.total_tokens
            by_model[model_key]["estimated_cost_usd"] += r.estimated_cost_usd
            by_model[model_key]["request_count"] += 1

            # Operation grouping
            op_key = r.operation_type
            if op_key not in by_operation:
                by_operation[op_key] = {
                    "operation_type": op_key,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "request_count": 0,
                }
            by_operation[op_key]["total_tokens"] += r.total_tokens
            by_operation[op_key]["estimated_cost_usd"] += r.estimated_cost_usd
            by_operation[op_key]["request_count"] += 1

        # Round totals
        for m in by_model.values():
            m["estimated_cost_usd"] = round(m["estimated_cost_usd"], 4)
        for o in by_operation.values():
            o["estimated_cost_usd"] = round(o["estimated_cost_usd"], 4)

        return {
            "organization_id": str(organization_id),
            "total_tokens": total_tokens,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_embedding_tokens": total_embedding_tokens,
            "total_estimated_cost_usd": round(total_estimated_cost, 4),
            "total_operations": len(records),
            "by_model": list(by_model.values()),
            "by_operation": list(by_operation.values()),
        }
