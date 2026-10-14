"""System information schemas."""

from pydantic import BaseModel, Field


class SystemInfoResponse(BaseModel):
    """Public platform identity, release, and engineering phase metadata."""

    app_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Platform version")
    environment: str = Field(..., description="Active deployment environment")
    phase: str = Field(
        default="Phase 00: Foundation & Standards",
        description="Current engineering phase",
    )
    architecture: str = Field(
        default="Modular Monolith with Domain Isolation",
        description="Architectural blueprint",
    )
    docs_url: str = Field(default="/docs", description="OpenAPI interactive specification URL")
