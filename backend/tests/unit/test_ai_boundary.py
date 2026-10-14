"""Unit tests verifying AI architectural boundary invariants and schemas."""

import pytest
from pydantic import ValidationError

from app.ai.provider import AIActionProposal, CompletionUsage, ModelResponse


def test_ai_action_proposal_invariants():
    """Verify that an AI action proposal strictly enforces the is_proposal invariant."""
    proposal = AIActionProposal(
        action_type="escalate_ticket",
        parameters={"priority": "high", "department": "tier_3_billing"},
        confidence=0.94,
        rationale="Customer reported billing discrepancy exceeding $500 with audit evidence.",
    )

    assert proposal.is_proposal is True
    assert proposal.confidence == 0.94
    assert proposal.action_type == "escalate_ticket"

    # Invariant: is_proposal cannot be mutated
    with pytest.raises(ValidationError):
        proposal.is_proposal = False  # frozen attribute


def test_ai_action_proposal_confidence_bounds():
    """Verify confidence must be bounded between 0.0 and 1.0."""
    with pytest.raises(ValidationError):
        AIActionProposal(
            action_type="draft_response",
            confidence=1.5,  # Out of range
            rationale="Test",
        )

    with pytest.raises(ValidationError):
        AIActionProposal(
            action_type="draft_response",
            confidence=-0.1,  # Out of range
            rationale="Test",
        )


def test_model_response_and_usage():
    """Verify normalized LLM completion response and usage statistics."""
    usage = CompletionUsage(prompt_tokens=150, completion_tokens=50, total_tokens=200)
    response = ModelResponse(
        content="I have verified your account details.",
        provider="anthropic",
        model="claude-3-5-sonnet",
        finish_reason="stop",
        usage=usage,
    )

    assert response.provider == "anthropic"
    assert response.usage.total_tokens == 200
    assert response.content == "I have verified your account details."
