"""FastAPI router for organization-scoped customer management."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import OrganizationContext, get_organization_context
from app.core.errors import ForbiddenException
from app.core.rbac import Permission
from app.db.session import get_db_session
from app.models.customer import Customer
from app.models.enums import CustomerStatus
from app.schemas.customer import (
    CustomerCreateRequest,
    CustomerListResponse,
    CustomerResponse,
)

router = APIRouter(prefix="/organizations/{organization_id}/customers", tags=["Customers"])


@router.get(
    "",
    response_model=CustomerListResponse,
    status_code=status.HTTP_200_OK,
    summary="List organization customers",
    description="Retrieve paginated list of customers for this organization.",
)
async def list_customers(
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=100, description="Max customers to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> CustomerListResponse:
    if not context.has_permission(Permission.CUSTOMERS_READ):
        raise ForbiddenException("Permission 'customers:read' required to view customers.")

    org_id = context.organization.id
    count_stmt = select(func.count(Customer.id)).where(Customer.organization_id == org_id)
    total = (await db.execute(count_stmt)).scalar_one()

    query = (
        select(Customer)
        .where(Customer.organization_id == org_id)
        .order_by(Customer.created_at.desc(), Customer.id.desc())
        .limit(limit)
        .offset(offset)
    )
    res = await db.execute(query)
    items = list(res.scalars().all())

    return CustomerListResponse(
        items=[CustomerResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer",
    description="Provision a customer record within the organization.",
)
async def create_customer(
    payload: CustomerCreateRequest,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CustomerResponse:
    if not context.has_permission(Permission.CUSTOMERS_WRITE):
        raise ForbiddenException("Permission 'customers:write' required to create customers.")

    customer = Customer(
        organization_id=context.organization.id,
        display_name=payload.display_name.strip(),
        company_name=payload.company_name.strip() if payload.company_name else None,
        external_customer_id=payload.external_customer_id.strip() if payload.external_customer_id else None,
        status=CustomerStatus.ACTIVE,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return CustomerResponse.model_validate(customer)
