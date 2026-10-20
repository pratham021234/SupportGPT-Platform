"""Request and response schemas for authentication and session management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import normalize_email
from app.models.enums import MembershipRole, MembershipStatus, UserStatus


class LoginRequest(BaseModel):
    """Payload for password-based user authentication."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., max_length=255, description="User account email address")
    password: str = Field(..., min_length=8, max_length=128, description="User password")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        return normalize_email(value)


class UserResponse(BaseModel):
    """Public user identity representation. Strictly excludes credential hashes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    status: UserStatus
    created_at: datetime
    last_login_at: datetime | None = None


class UserOrganizationSummary(BaseModel):
    """Organization metadata and membership role associated with an authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    name: str
    slug: str
    role: MembershipRole
    status: MembershipStatus


class LoginResponse(BaseModel):
    """Authentication response payload containing user profile and available organizations."""

    user: UserResponse
    expires_at: datetime
    token: str | None = Field(
        default=None, description="Optional bearer token for non-browser API clients"
    )
    organizations: list[UserOrganizationSummary]


class CurrentUserResponse(BaseModel):
    """Detailed profile representation for the active user."""

    user: UserResponse
    organizations: list[UserOrganizationSummary]


class LogoutResponse(BaseModel):
    """Response confirming successful session termination."""

    message: str = "Session successfully terminated."
