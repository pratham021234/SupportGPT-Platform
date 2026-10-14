"""Organization workspace model and concurrency-safe ticket counter."""

import re
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import OrganizationStatus


def normalize_organization_slug(raw_slug: str) -> str:
    """Normalize organization slug to lowercase alphanumeric with single hyphens."""
    slug = raw_slug.strip().lower()
    # Replace any character other than [a-z0-9] with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    if not slug:
        raise ValueError("Organization slug must contain at least one alphanumeric character.")
    if len(slug) > 100:
        slug = slug[:100].rstrip("-")
    return slug


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authoritative customer workspace tenant entity."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable enterprise display name",
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="Normalized unique workspace slug identifier",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=OrganizationStatus.ACTIVE,
        nullable=False,
        comment="Workspace lifecycle status",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional soft-deletion timestamp",
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN ('{OrganizationStatus.ACTIVE}', '{OrganizationStatus.SUSPENDED}', '{OrganizationStatus.ARCHIVED}')",
            name="ck_organizations_valid_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug='{self.slug}', status='{self.status}')>"


class OrganizationTicketCounter(Base):
    """Concurrency-safe transactional counter table for sequential per-organization ticket numbers."""

    __tablename__ = "organization_ticket_counters"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        primary_key=True,
        comment="Organization scope for the counter",
    )
    next_ticket_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="Next sequential ticket number to allocate",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("next_ticket_number >= 1", name="ck_ticket_counter_positive"),
    )

    def __repr__(self) -> str:
        return f"<OrganizationTicketCounter(org_id={self.organization_id}, next={self.next_ticket_number})>"


async def allocate_next_ticket_number(session: AsyncSession, organization_id: uuid.UUID) -> int:
    """Atomically allocate the next sequential ticket number for an organization.

    Uses PostgreSQL row-level locking (SELECT FOR UPDATE) to guarantee concurrency safety
    without gaps or race conditions.
    """
    stmt = (
        select(OrganizationTicketCounter)
        .where(OrganizationTicketCounter.organization_id == organization_id)
        .with_for_update()
    )
    res = await session.execute(stmt)
    counter = res.scalar_one_or_none()

    if counter is None:
        # Initialize counter starting at 1
        counter = OrganizationTicketCounter(organization_id=organization_id, next_ticket_number=2)
        session.add(counter)
        await session.flush()
        return 1

    allocated = counter.next_ticket_number
    counter.next_ticket_number = allocated + 1
    await session.flush()
    return allocated
