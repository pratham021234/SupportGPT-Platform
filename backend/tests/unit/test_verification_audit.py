"""Unit tests for verification audit event recording and query operations."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import VerificationAuditEventType
from app.services.verification.audit_service import VerificationAuditService


@pytest.mark.asyncio
async def test_record_audit_event():
    """Verify record_event adds and flushes a structured audit log entry."""
    org_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    event = await VerificationAuditService.record_event(
        session=mock_session,
        organization_id=org_id,
        event_type=VerificationAuditEventType.DRAFT_CREATED,
        entity_type="draft",
        entity_id=draft_id,
        event_summary="Created draft v1",
        actor_id=actor_id,
        metadata_json={"version": 1},
    )

    assert event.organization_id == org_id
    assert event.event_type == VerificationAuditEventType.DRAFT_CREATED.value
    assert event.entity_type == "draft"
    assert event.entity_id == draft_id
    assert event.actor_id == actor_id
    assert event.metadata_json == {"version": 1}
    mock_session.add.assert_called_once_with(event)
    mock_session.flush.assert_called_once()
