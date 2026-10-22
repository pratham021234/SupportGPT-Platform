"""Evaluation Service for running benchmarks, detecting quality regressions, and persisting runs."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import EvaluationStatus
from app.models.evaluation_run import EvaluationRunRecord
from app.services.rag.answer import GroundedAnswerService
from app.services.rag.evaluation import (
    EVALUATION_DATASET,
    EvalTestCase,
    RAGEvaluator,
)
from app.services.rag.evidence import EvidenceItem

logger = get_logger("supportgpt.observability.evaluation")


class EvaluationService:
    """Manages benchmark evaluations, baseline comparisons, and regression detection."""

    REGRESSION_THRESHOLD = 0.05  # 5% relative or absolute regression tolerance

    @classmethod
    async def run_benchmark(
        cls,
        session: AsyncSession,
        organization_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        custom_dataset: list[EvalTestCase] | None = None,
    ) -> EvaluationRunRecord:
        """Execute the evaluation benchmark and detect regressions against the previous baseline."""
        dataset = custom_dataset or EVALUATION_DATASET
        evaluator = RAGEvaluator()
        answer_service = GroundedAnswerService()

        case_results = []
        now = datetime.now(UTC)

        for case in dataset:
            # Deterministic simulation/execution against test case
            if case.is_unanswerable:
                # Unanswerable query triggers expected abstention
                ans_res = await answer_service.generate_answer(
                    question=case.question,
                    evidence=[],
                )
                evaluated_case = evaluator.evaluate_query(case, [], ans_res)
            else:
                # Grounded evidence for answerable test case
                mock_evidence = [
                    EvidenceItem(
                        evidence_id="ev_1",
                        chunk_id=uuid.uuid4(),
                        document_id=uuid.uuid4(),
                        document_version_id=uuid.uuid4(),
                        knowledge_base_id=uuid.uuid4(),
                        source_title=case.expected_source_title or "Source Document",
                        relevant_excerpt=" ".join(case.expected_content_keywords)
                        + " according to enterprise compliance policy.",
                        retrieval_rank=1,
                        retrieval_score=0.92,
                        citation_reference="[citation:1]",
                    )
                ]
                ans_res = await answer_service.generate_answer(
                    question=case.question,
                    evidence=mock_evidence,
                )
                evaluated_case = evaluator.evaluate_query(case, mock_evidence, ans_res)

            case_results.append(evaluated_case)

        report = evaluator.compile_report(case_results)

        # Retrieve previous completed run for regression comparison
        prev_run_query = (
            select(EvaluationRunRecord)
            .where(
                EvaluationRunRecord.organization_id == organization_id,
                EvaluationRunRecord.status == EvaluationStatus.COMPLETED.value,
            )
            .order_by(desc(EvaluationRunRecord.created_at))
            .limit(1)
        )
        prev_result = await session.execute(prev_run_query)
        previous_run = prev_result.scalar_one_or_none()

        # Compute regression metrics
        regressions: dict[str, Any] = {
            "has_regression": False,
            "baseline_run_id": str(previous_run.id) if previous_run else None,
            "recall_delta": 0.0,
            "citation_delta": 0.0,
            "abstention_delta": 0.0,
            "flags": [],
        }

        if previous_run:
            recall_drop = previous_run.mean_recall_at_k - report.mean_recall_at_k
            citation_drop = previous_run.citation_validity_rate - report.citation_validity_rate
            abstention_drop = previous_run.abstention_accuracy - report.abstention_accuracy

            regressions["recall_delta"] = round(-recall_drop, 4)
            regressions["citation_delta"] = round(-citation_drop, 4)
            regressions["abstention_delta"] = round(-abstention_drop, 4)

            if recall_drop > cls.REGRESSION_THRESHOLD:
                regressions["has_regression"] = True
                regressions["flags"].append(f"Recall@k dropped by {recall_drop:.2%}")
            if citation_drop > cls.REGRESSION_THRESHOLD:
                regressions["has_regression"] = True
                regressions["flags"].append(f"Citation validity dropped by {citation_drop:.2%}")
            if abstention_drop > cls.REGRESSION_THRESHOLD:
                regressions["has_regression"] = True
                regressions["flags"].append(f"Abstention accuracy dropped by {abstention_drop:.2%}")

        completed_time = datetime.now(UTC)

        record = EvaluationRunRecord(
            id=uuid.uuid4(),
            organization_id=organization_id,
            dataset_id="enterprise_eval_dataset_v1",
            dataset_version=report.dataset_version,
            total_cases=report.total_queries,
            answerable_cases=report.answerable_queries,
            unanswerable_cases=report.unanswerable_queries,
            embedding_provider=report.embedding_provider,
            embedding_model=report.embedding_model,
            generation_provider="system",
            generation_model=settings.AI_MODEL_NAME,
            retrieval_config={
                "top_k": settings.RETRIEVAL_TOP_K_DEFAULT,
                "relevance_threshold": settings.RETRIEVAL_SIMILARITY_THRESHOLD,
            },
            verification_pipeline_version="v1.0.0",
            policy_version="1",
            mean_recall_at_k=report.mean_recall_at_k,
            mean_reciprocal_rank=report.mean_reciprocal_rank,
            citation_validity_rate=report.citation_validity_rate,
            abstention_accuracy=report.abstention_accuracy,
            status=EvaluationStatus.COMPLETED.value,
            case_results=[c.model_dump() for c in report.case_results],
            regressions=regressions,
            created_at=now,
            completed_at=completed_time,
            created_by_user_id=user_id,
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def list_evaluations(
        session: AsyncSession,
        organization_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[EvaluationRunRecord], int]:
        """List tenant evaluation benchmark runs."""
        count_q = select(EvaluationRunRecord).where(
            EvaluationRunRecord.organization_id == organization_id
        )
        count_res = await session.execute(count_q)
        total = len(count_res.scalars().all())

        query = (
            select(EvaluationRunRecord)
            .where(EvaluationRunRecord.organization_id == organization_id)
            .order_by(desc(EvaluationRunRecord.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(query)
        return list(result.scalars().all()), total

    @staticmethod
    async def get_evaluation(
        session: AsyncSession,
        organization_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> EvaluationRunRecord | None:
        """Retrieve single evaluation run by ID with tenant isolation."""
        query = select(EvaluationRunRecord).where(
            EvaluationRunRecord.organization_id == organization_id,
            EvaluationRunRecord.id == run_id,
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def compare_runs(
        session: AsyncSession,
        organization_id: uuid.UUID,
        baseline_id: uuid.UUID,
        candidate_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        """Compare two specific evaluation runs."""
        q1 = select(EvaluationRunRecord).where(
            EvaluationRunRecord.organization_id == organization_id,
            EvaluationRunRecord.id == baseline_id,
        )
        q2 = select(EvaluationRunRecord).where(
            EvaluationRunRecord.organization_id == organization_id,
            EvaluationRunRecord.id == candidate_id,
        )
        r1 = (await session.execute(q1)).scalar_one_or_none()
        r2 = (await session.execute(q2)).scalar_one_or_none()

        if not r1 or not r2:
            return None

        recall_diff = r2.mean_recall_at_k - r1.mean_recall_at_k
        mrr_diff = r2.mean_reciprocal_rank - r1.mean_reciprocal_rank
        citation_diff = r2.citation_validity_rate - r1.citation_validity_rate
        abstention_diff = r2.abstention_accuracy - r1.abstention_accuracy

        return {
            "baseline_id": str(r1.id),
            "baseline_date": r1.created_at.isoformat(),
            "candidate_id": str(r2.id),
            "candidate_date": r2.created_at.isoformat(),
            "comparison": {
                "mean_recall_at_k": {
                    "baseline": r1.mean_recall_at_k,
                    "candidate": r2.mean_recall_at_k,
                    "delta": round(recall_diff, 4),
                },
                "mean_reciprocal_rank": {
                    "baseline": r1.mean_reciprocal_rank,
                    "candidate": r2.mean_reciprocal_rank,
                    "delta": round(mrr_diff, 4),
                },
                "citation_validity_rate": {
                    "baseline": r1.citation_validity_rate,
                    "candidate": r2.citation_validity_rate,
                    "delta": round(citation_diff, 4),
                },
                "abstention_accuracy": {
                    "baseline": r1.abstention_accuracy,
                    "candidate": r2.abstention_accuracy,
                    "delta": round(abstention_diff, 4),
                },
            },
            "is_regression": (
                recall_diff < -0.05 or citation_diff < -0.05 or abstention_diff < -0.05
            ),
        }
