"""Unit tests for provider event parsing and canonical normalization."""

import uuid

import pytest

from app.core.errors import EventNormalizationException
from app.models.enums import SourceProvider, TicketPriority
from app.models.event_source import EventSource
from app.services.event_normalizer import EventNormalizer


def test_standard_webhook_normalization_ticket_created():
    """Verify complete extraction of ticket.created payload into CanonicalEvent."""
    source = EventSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        provider=SourceProvider.GENERIC_WEBHOOK,
        name="Test Webhook",
        signing_secret_hash="hash",
    )
    raw_payload = {
        "event_id": "evt-alpha-999",
        "event_type": "ticket.created",
        "timestamp": 1700000000,
        "subject": "System Outage on Login",
        "description": "Users cannot log in to the portal since 10am.",
        "priority": "urgent",
        "customer": {
            "email": "customer@acme.com",
            "name": "Jane Doe",
            "external_id": "cust-ext-456",
        },
        "ticket": {
            "id": "ext-tick-101",
        },
        "metadata": {
            "source_ip": "1.2.3.4",
        },
    }

    event = EventNormalizer.normalize(source, raw_payload)

    assert event.external_event_id == "evt-alpha-999"
    assert event.event_type == "ticket.created"
    assert event.subject == "System Outage on Login"
    assert event.message_body == "Users cannot log in to the portal since 10am."
    assert event.priority == TicketPriority.URGENT
    assert event.external_ticket_id == "ext-tick-101"
    assert event.customer is not None
    assert event.customer.email == "customer@acme.com"
    assert event.customer.name == "Jane Doe"
    assert event.customer.external_id == "cust-ext-456"
    assert event.metadata == {"source_ip": "1.2.3.4"}


def test_standard_webhook_normalization_message_received():
    """Verify complete extraction of message.received payload into CanonicalEvent."""
    source = EventSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        provider=SourceProvider.CUSTOM_API,
        name="Chat API",
        signing_secret_hash="hash",
    )
    raw_payload = {
        "id": "evt-msg-555",
        "type": "message.received",
        "ticket_id": "ext-tick-101",
        "message_id": "ext-msg-777",
        "body": "Here is the screenshot of the error.",
        "customer_email": "jane@acme.com",
    }

    event = EventNormalizer.normalize(source, raw_payload)

    assert event.external_event_id == "evt-msg-555"
    assert event.event_type == "message.received"
    assert event.external_ticket_id == "ext-tick-101"
    assert event.external_message_id == "ext-msg-777"
    assert event.message_body == "Here is the screenshot of the error."
    assert event.customer is not None
    assert event.customer.email == "jane@acme.com"


def test_missing_event_id_raises_normalization_error():
    """Events lacking an identifier are rejected."""
    source = EventSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        provider=SourceProvider.GENERIC_WEBHOOK,
        name="Test",
        signing_secret_hash="hash",
    )
    raw_payload = {
        "event_type": "ticket.created",
        "body": "No ID here",
    }

    with pytest.raises(EventNormalizationException):
        EventNormalizer.normalize(source, raw_payload)


def test_missing_event_type_raises_normalization_error():
    """Events lacking an event type are rejected."""
    source = EventSource(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        provider=SourceProvider.GENERIC_WEBHOOK,
        name="Test",
        signing_secret_hash="hash",
    )
    raw_payload = {
        "event_id": "evt-123",
        "body": "No type here",
    }

    with pytest.raises(EventNormalizationException):
        EventNormalizer.normalize(source, raw_payload)
