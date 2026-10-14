"""AI Provider Architectural Boundary and Abstractions.

Defines vendor-agnostic contracts for Large Language Models, Embedding engines,
structured outputs, and AI-proposed actions. Core domain logic must never couple
directly to proprietary provider SDKs.
"""

from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class ChatMessage(BaseModel):
    """Normalized chat message representation."""

    role: str = Field(..., description="Message author role: system, user, assistant, or tool")
    content: str = Field(..., description="Text content of the message")
    name: str | None = Field(
        default=None, description="Optional name identifier for tool or participant"
    )


class CompletionUsage(BaseModel):
    """Normalized token accounting for metering and billing."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ModelResponse(BaseModel):
    """Standardized response container returned by any compliant LLM provider."""

    content: str = Field(..., description="Generated completion text")
    provider: str = Field(..., description="Provider name (e.g. anthropic, openai, local)")
    model: str = Field(..., description="Specific model identifier employed")
    finish_reason: str | None = Field(default=None, description="Completion finish reason")
    usage: CompletionUsage = Field(default_factory=CompletionUsage)


class AIActionProposal(BaseModel):
    """Formal representation of an action proposed by an AI model.

    SECURITY INVARIANT:
    Any AI-generated action must be treated as a proposal, not as authorization.
    All actions must pass through human approval or policy enforcement prior to execution.
    """

    action_type: str = Field(
        ..., description="Identifies the proposed operation (e.g. refund, escalate, draft_reply)"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Parameters proposed by the AI"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Model-reported or verification confidence score"
    )
    rationale: str = Field(
        ..., description="Explanation and ground evidence supporting the proposal"
    )
    is_proposal: bool = Field(
        default=True,
        frozen=True,
        description="Enforces that this structure cannot represent authorized execution",
    )


class BaseLLMProvider(ABC):
    """Vendor-neutral interface for completion and structured generation."""

    @abstractmethod
    async def generate_completion(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> ModelResponse:
        """Generate a raw text completion from input messages."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[ChatMessage],
        output_schema: type[T],
        temperature: float = 0.1,
    ) -> T:
        """Generate a response strictly validated against a Pydantic schema."""
        pass


class BaseEmbeddingProvider(ABC):
    """Vendor-neutral interface for semantic vector generation."""

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for an ordered batch of text chunks."""
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """Generate a vector embedding for a single search or retrieval query."""
        pass
