"""Standardized error response schemas conforming to enterprise API conventions."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Specific error field or invariant violation detail."""

    field: str | None = Field(
        default=None, description="Request field name where validation failed"
    )
    message: str = Field(..., description="Human-readable explanation of the specific violation")
    code: str | None = Field(default=None, description="Machine-readable error subtype code")


class ErrorBody(BaseModel):
    """Structured envelope containing error metadata."""

    code: str = Field(..., description="High-level machine-readable error code")
    message: str = Field(..., description="Human-readable summary of the error")
    details: list[ErrorDetail] = Field(default_factory=list, description="Granular error details")
    request_id: str | None = Field(default=None, description="Request correlation identifier")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="UTC ISO timestamp of the error event",
    )


class ErrorResponse(BaseModel):
    """Standardized root error payload."""

    error: ErrorBody
