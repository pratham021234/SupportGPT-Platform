"""Health and readiness response schemas."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthStatusResponse(BaseModel):
    """Liveness probe response indicating process availability."""

    status: Literal["ok"] = Field(default="ok", description="Process liveness state")
    app: str = Field(..., description="Application name")
    environment: str = Field(..., description="Running environment")
    version: str = Field(..., description="Semantic application version")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Current UTC timestamp",
    )


class DependencyHealth(BaseModel):
    """Health indicator for an individual external service dependency."""

    status: Literal["up", "down", "skipped", "degraded"] = Field(
        ..., description="Dependency status indicator"
    )
    latency_ms: float | None = Field(
        default=None, description="Round-trip probe latency in milliseconds"
    )
    error: str | None = Field(
        default=None,
        description="Sanitized non-sensitive probe error summary if unavailable",
    )


class ReadinessResponse(BaseModel):
    """Readiness probe response indicating ability to serve traffic."""

    status: Literal["ready", "degraded"] = Field(
        ..., description="Overall platform traffic readiness"
    )
    environment: str = Field(..., description="Active environment")
    dependencies: dict[str, DependencyHealth] = Field(
        ..., description="Map of probed external dependencies"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Probe execution timestamp",
    )
