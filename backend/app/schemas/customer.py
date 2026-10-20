"""Pydantic schemas for customer entities and customer listing."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CustomerStatus


class CustomerResponse(BaseModel):
    """Public representation of an organization customer."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    display_name: str
    company_name: str | None = None
    external_customer_id: str | None = None
    status: CustomerStatus
    created_at: datetime
    updated_at: datetime


class CustomerCreateRequest(BaseModel):
    """Payload to create a new customer record within an organization."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(
        ..., min_length=1, max_length=255, description="Full name or contact title"
    )
    company_name: str | None = Field(
        default=None, max_length=255, description="Optional organization name"
    )
    external_customer_id: str | None = Field(
        default=None, max_length=255, description="Optional CRM identifier"
    )


class CustomerListResponse(BaseModel):
    """Paginated list of customer records."""

    items: list[CustomerResponse]
    total: int
    limit: int
    offset: int
