"""Unit tests for Observability Services: failure classification, usage calculations, and regression testing."""

from app.models.enums import FailureCategory
from app.services.observability.evaluation_service import EvaluationService
from app.services.observability.investigation_service import InvestigationService
from app.services.observability.usage_service import UsageAccountingService


def test_failure_classification_mapping() -> None:
    # Authentication & Authorization
    assert (
        InvestigationService.classify_failure("User authentication token invalid or expired")
        == FailureCategory.AUTHENTICATION_ERROR.value
    )
    assert (
        InvestigationService.classify_failure("Operation forbidden: separation of duties policy")
        == FailureCategory.AUTHORIZATION_ERROR.value
    )

    # Retrieval & Evidence
    assert (
        InvestigationService.classify_failure("Qdrant vector search failed to connect")
        == FailureCategory.RETRIEVAL_FAILURE.value
    )
    assert (
        InvestigationService.classify_failure("No relevant evidence found in knowledge base")
        == FailureCategory.NO_RELEVANT_EVIDENCE.value
    )

    # Answering & Verification
    assert (
        InvestigationService.classify_failure("Hallucinated citation marker [citation:99] detected")
        == FailureCategory.CITATION_VALIDATION_FAILURE.value
    )
    assert (
        InvestigationService.classify_failure("Draft has unsupported claim regarding refund policy")
        == FailureCategory.VERIFICATION_FAILURE.value
    )
    assert (
        InvestigationService.classify_failure("Prohibited term 'guarantee' found in draft response")
        == FailureCategory.POLICY_VIOLATION.value
    )


def test_diagnostic_hypotheses_generation() -> None:
    # No relevant evidence
    hypotheses = InvestigationService.generate_hypotheses(
        FailureCategory.NO_RELEVANT_EVIDENCE.value, "Abstaining: no evidence"
    )
    assert len(hypotheses) >= 1
    assert any("indexed" in h["hypothesis"].lower() for h in hypotheses)
    assert any("threshold" in h["hypothesis"].lower() for h in hypotheses)

    # Policy violation
    policy_hypo = InvestigationService.generate_hypotheses(
        FailureCategory.POLICY_VIOLATION.value, "Prohibited keyword triggered"
    )
    assert len(policy_hypo) >= 1
    assert "prohibited" in policy_hypo[0]["hypothesis"].lower()
    assert "policy" in policy_hypo[0]["recommended_action"].lower()


def test_token_cost_calculation_rates() -> None:
    # OpenAI GPT-4o: 1,000 input tokens ($0.0025) + 500 output tokens ($0.0050) = $0.0075
    cost, tier = UsageAccountingService.calculate_cost(
        provider="openai",
        model="gpt-4o",
        input_tokens=1000,
        output_tokens=500,
        embedding_tokens=0,
    )
    assert cost == 0.0075
    assert tier == "openai-2026-q1"

    # OpenAI GPT-4o-mini: 10,000 input tokens ($0.0015) + 1,000 output tokens ($0.0006) = $0.0021
    cost_mini, tier_mini = UsageAccountingService.calculate_cost(
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=10000,
        output_tokens=1000,
        embedding_tokens=0,
    )
    assert cost_mini == 0.0021
    assert tier_mini == "openai-2026-q1"

    # FastEmbed Local ONNX: $0.00 cost
    cost_local, tier_local = UsageAccountingService.calculate_cost(
        provider="fastembed",
        model="BAAI/bge-small-en-v1.5",
        input_tokens=0,
        output_tokens=0,
        embedding_tokens=5000,
    )
    assert cost_local == 0.0
    assert tier_local == "local-onnx-free"


def test_regression_tolerance_threshold() -> None:
    # Regression threshold is 0.05 (5%)
    assert EvaluationService.REGRESSION_THRESHOLD == 0.05
