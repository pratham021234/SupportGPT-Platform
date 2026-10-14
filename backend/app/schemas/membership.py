"""Request and response schemas for organization membership and RBAC management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import normalize_email
from app.models.enums import MembershipRole, MembershipStatus


class MemberResponse(BaseModel):
    """Public representation of an organization member."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    display_name: str
    role: MembershipRole
    status: MembershipStatus
    created_at: datetime


class AddMemberRequest(BaseModel):
    """Payload to invite or register a new member in an organization."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., max_length=255, description="Email of the user to invite/add")
    display_name: str = Field(..., min_length=1, max_length=150, description="Display name for the user")
    role: MembershipRole = Field(default=MembershipRole.AGENT, description="Role to assign to the user")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        return normalize_email(value)


class UpdateMemberRoleRequest(BaseModel):
    """Payload to modify an existing member's role."""

    model_config = ConfigDict(extra="forbid")

    role: MembershipRole = Field(..., description="Target role to assign")


class MembershipDetailResponse(BaseModel):
    """Detailed representation of caller's membership including effective permissions."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    user_id: uuid.UUID
    role: MembershipRole
    status: MembershipStatus
    permissions: list[str]
    created_at: datetime
