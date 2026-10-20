"""Append-only audit logging service for verification and human approval events."""

import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import VerificationAuditEventType
from app.models.verification_audit_event import VerificationAuditEvent


class VerificationAuditService:
    """Provides append-only auditing and query capabilities for compliance records."""

    @staticmethod
    async def record_event(
        session: AsyncSession,
        organization_id: uuid.UUID,
        event_type: VerificationAuditEventType | str,
        entity_type: str,
        entity_id: uuid.UUID,
        event_summary: str,
        actor_id: uuid.UUID | None = None,
        request_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> VerificationAuditEvent:
        """Create and flush an immutable audit event record."""
        event_str = (
            event_type.value
            if isinstance(event_type, VerificationAuditEventType)
            else str(event_type)
        )

        audit_entry = VerificationAuditEvent(
            organization_id=organization_id,
            event_type=event_str,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            request_id=request_id,
            event_summary=event_summary,
            metadata_json=metadata_json or {},
        )
        session.add(audit_entry)
        await session.flush()
        return audit_entry

    @staticmethod
    async def list_audit_events(
        session: AsyncSession,
        organization_id: uuid.UUID,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VerificationAuditEvent]:
        """Query audit log records for an organization with optional filtering."""
        stmt = (
            select(VerificationAuditEvent)
            .where(VerificationAuditEvent.organization_id == organization_id)
            .order_by(desc(VerificationAuditEvent.created_at))
            .limit(min(limit, 100))
            .offset(offset)
        )

        if entity_type:
            stmt = stmt.where(VerificationAuditEvent.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(VerificationAuditEvent.entity_id == entity_id)
        if event_type:
            stmt = stmt.where(VerificationAuditEvent.event_type == event_type)

        res = await session.execute(stmt)
        return list(res.scalars().all())
