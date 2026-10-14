"""Unit tests verifying domain model normalization, status transitions, and enum mappings."""

import uuid

import pytest

from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.customer_identity import CustomerIdentity, normalize_identity_value
from app.models.enums import (
    AttachmentScanStatus,
    AuthorType,
    ConversationStatus,
    CustomerStatus,
    IdentityType,
    IdentityVerificationStatus,
    IngestionStatus,
    MessageDirection,
    OrganizationStatus,
    TicketChannel,
    TicketPriority,
    TicketStatus,
    can_transition_ticket_status,
)
from app.models.ingestion_receipt import IngestionReceipt
from app.models.message import Message
from app.models.organization import Organization, normalize_organization_slug
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent


def test_organization_slug_normalization():
    """Verify organization slug normalization rules."""
    assert normalize_organization_slug("Acme Corp") == "acme-corp"
    assert normalize_organization_slug("  Acme  -- Corp!! ") == "acme-corp"
    assert normalize_organization_slug("alpha-123_beta") == "alpha-123-beta"

    # Empty or purely invalid slugs must raise ValueError
    with pytest.raises(ValueError, match="at least one alphanumeric character"):
        normalize_organization_slug("   --- !!!   ")


def test_customer_identity_normalization():
    """Verify contact identity normalization rules."""
    # Email normalization
    assert (
        normalize_identity_value(IdentityType.EMAIL, "  Alice.Smith@Example.COM  ")
        == "alice.smith@example.com"
    )

    # Phone normalization
    assert normalize_identity_value(IdentityType.PHONE, "+1 (555) 123-4567") == "+15551234567"
    assert normalize_identity_value(IdentityType.PHONE, "555-9876") == "5559876"

    # Empty identity raises ValueError
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_identity_value(IdentityType.EMAIL, "   ")


def test_ticket_status_transitions():
    """Verify permissible and forbidden ticket status transitions."""
    # Permissible transitions
    assert can_transition_ticket_status(TicketStatus.OPEN, TicketStatus.IN_PROGRESS) is True
    assert can_transition_ticket_status(TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED) is True
    assert can_transition_ticket_status(TicketStatus.RESOLVED, TicketStatus.CLOSED) is True
    assert can_transition_ticket_status(TicketStatus.RESOLVED, TicketStatus.OPEN) is True  # re-open
    assert (
        can_transition_ticket_status(TicketStatus.OPEN, TicketStatus.OPEN) is True
    )  # self-transition

    # Forbidden transitions
    assert can_transition_ticket_status(TicketStatus.CLOSED, TicketStatus.PENDING) is False
    assert can_transition_ticket_status(TicketStatus.CLOSED, TicketStatus.IN_PROGRESS) is False


def test_model_instantiation_and_defaults():
    """Verify that all canonical domain entities instantiate with expected defaults."""
    org_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    tick_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()

    org = Organization(name="Stripe", slug="stripe", status=OrganizationStatus.ACTIVE)
    assert org.slug == "stripe"
    assert org.status == OrganizationStatus.ACTIVE

    cust = Customer(organization_id=org_id, display_name="Bob Jones", status=CustomerStatus.ACTIVE)
    assert cust.display_name == "Bob Jones"
    assert cust.company_name is None

    ident = CustomerIdentity(
        organization_id=org_id,
        customer_id=cust_id,
        identity_type=IdentityType.EMAIL,
        normalized_value="bob@example.com",
        verification_status=IdentityVerificationStatus.UNVERIFIED,
    )
    assert ident.normalized_value == "bob@example.com"
    assert ident.verification_status == IdentityVerificationStatus.UNVERIFIED

    ticket = Ticket(
        organization_id=org_id,
        ticket_number=101,
        ticket_reference="TICK-101",
        subject="Password reset request",
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
        channel=TicketChannel.EMAIL,
    )
    assert ticket.status == TicketStatus.OPEN
    assert ticket.priority == TicketPriority.MEDIUM
    assert ticket.channel == TicketChannel.EMAIL

    conv = Conversation(
        organization_id=org_id,
        ticket_id=tick_id,
        channel_type=TicketChannel.EMAIL,
        status=ConversationStatus.ACTIVE,
    )
    assert conv.status == ConversationStatus.ACTIVE

    msg = Message(
        organization_id=org_id,
        conversation_id=conv_id,
        direction=MessageDirection.INBOUND,
        author_type=AuthorType.CUSTOMER,
        body_text="Help with reset link",
        content_type="text/plain",
    )
    assert msg.direction == MessageDirection.INBOUND
    assert msg.content_type == "text/plain"

    att = Attachment(
        organization_id=org_id,
        message_id=msg_id,
        filename="screenshot.png",
        storage_key="org/123/att/456.png",
        content_type="image/png",
        size_bytes=1024,
        scan_status=AttachmentScanStatus.PENDING,
    )
    assert att.scan_status == AttachmentScanStatus.PENDING
    assert att.size_bytes == 1024

    event = TicketEvent(
        organization_id=org_id,
        ticket_id=tick_id,
        event_type="status_changed",
        actor_type=AuthorType.AGENT,
    )
    assert event.event_type == "status_changed"

    receipt = IngestionReceipt(
        organization_id=org_id,
        source_provider="sendgrid",
        external_event_id="evt_sg_9999",
        event_type="inbound_email",
        status=IngestionStatus.RECEIVED,
    )
    assert receipt.status == IngestionStatus.RECEIVED
