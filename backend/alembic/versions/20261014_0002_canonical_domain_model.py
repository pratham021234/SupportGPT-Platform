"""Canonical customer support domain models and multi-tenant schema foundation.

Revision ID: 0002_canonical_domain_model
Revises: 0001_initial_foundation
Create Date: 2026-10-14 10:25:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_canonical_domain_model"
down_revision: str | None = "0001_initial_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Organizations table
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            comment="Human-readable enterprise display name",
        ),
        sa.Column(
            "slug",
            sa.String(length=100),
            nullable=False,
            comment="Normalized unique workspace slug identifier",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
            comment="Workspace lifecycle status",
        ),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Optional soft-deletion timestamp",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'archived')",
            name=op.f("ck_organizations_valid_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)

    # 2. Organization ticket counter table
    op.create_table(
        "organization_ticket_counters",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope for the counter",
        ),
        sa.Column(
            "next_ticket_number",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="Next sequential ticket number to allocate",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_ticket_counters_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("organization_id", name=op.f("pk_organization_ticket_counters")),
        sa.CheckConstraint("next_ticket_number >= 1", name=op.f("ck_ticket_counter_positive")),
    )

    # 3. Customers table
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization owning this customer record",
        ),
        sa.Column(
            "display_name",
            sa.String(length=255),
            nullable=False,
            comment="Human-readable customer name",
        ),
        sa.Column(
            "company_name",
            sa.String(length=255),
            nullable=True,
            comment="Optional customer organization or business affiliation",
        ),
        sa.Column(
            "external_customer_id",
            sa.String(length=255),
            nullable=True,
            comment="Optional identifier from external CRM or customer datastore",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
            comment="Customer lifecycle state",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_customers_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("id", "organization_id", name="uq_customers_id_organization_id"),
        sa.CheckConstraint(
            "status IN ('active', 'blocked', 'merged')",
            name=op.f("ck_customers_valid_status"),
        ),
    )
    op.create_index(
        op.f("ix_customers_organization_id"),
        "customers",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_customers_org_external_id",
        "customers",
        ["organization_id", "external_customer_id"],
        unique=False,
    )
    op.create_index(
        "ix_customers_org_status",
        "customers",
        ["organization_id", "status"],
        unique=False,
    )

    # 4. Customer Identities table
    op.create_table(
        "customer_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope for this identity",
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Customer owning this identity",
        ),
        sa.Column(
            "identity_type",
            sa.String(length=30),
            nullable=False,
            comment="Identity category (email, phone, external_channel, provider_specific)",
        ),
        sa.Column(
            "normalized_value",
            sa.String(length=320),
            nullable=False,
            comment="Canonical normalized value used for lookups and deduplication",
        ),
        sa.Column(
            "raw_value",
            sa.String(length=320),
            nullable=True,
            comment="Original unnormalized representation for display",
        ),
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=True,
            comment="Optional channel or provider source identifier",
        ),
        sa.Column(
            "verification_status",
            sa.String(length=20),
            server_default="unverified",
            nullable=False,
            comment="Verification state of this contact method",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_customer_identities_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_customer_identities_customer_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_identities")),
        sa.UniqueConstraint(
            "organization_id",
            "identity_type",
            "normalized_value",
            name="uq_customer_identities_org_type_val",
        ),
        sa.CheckConstraint(
            "identity_type IN ('email', 'phone', 'external_channel', 'provider_specific')",
            name=op.f("ck_customer_identities_valid_type"),
        ),
        sa.CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'revoked')",
            name=op.f("ck_customer_identities_valid_verification"),
        ),
    )
    op.create_index(
        op.f("ix_customer_identities_organization_id"),
        "customer_identities",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_customer_identities_customer_id"),
        "customer_identities",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        "ix_customer_identities_lookup",
        "customer_identities",
        ["organization_id", "normalized_value"],
        unique=False,
    )

    # 5. Tickets table
    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization owning this support ticket",
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Optional customer initiating or associated with the ticket",
        ),
        sa.Column(
            "ticket_number",
            sa.Integer(),
            nullable=False,
            comment="Sequential human-readable ticket number allocated per organization",
        ),
        sa.Column(
            "ticket_reference",
            sa.String(length=50),
            nullable=False,
            comment="Formatted public ticket reference code (e.g. TICK-1001)",
        ),
        sa.Column(
            "subject",
            sa.String(length=500),
            nullable=False,
            comment="Summary headline of the support request",
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="open",
            nullable=False,
            comment="Operational ticket status",
        ),
        sa.Column(
            "priority",
            sa.String(length=20),
            server_default="medium",
            nullable=False,
            comment="Ticket urgency / priority tier",
        ),
        sa.Column(
            "channel",
            sa.String(length=30),
            server_default="email",
            nullable=False,
            comment="Initial ingestion channel for the ticket",
        ),
        sa.Column(
            "assigned_actor_id",
            sa.String(length=100),
            nullable=True,
            comment="Assigned agent or system actor identifier",
        ),
        sa.Column(
            "first_response_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of first outbound agent/system reply",
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when ticket status transitioned to resolved",
        ),
        sa.Column(
            "closed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when ticket status transitioned to closed",
        ),
        sa.Column(
            "external_reference",
            sa.String(length=255),
            nullable=True,
            comment="Optional source reference ID from external ticketing systems",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Structured metadata associated with the ticket",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_tickets_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["customer_id", "organization_id"],
            ["customers.id", "customers.organization_id"],
            name="fk_tickets_customer_org",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("id", "organization_id", name="uq_tickets_id_organization_id"),
        sa.UniqueConstraint(
            "organization_id", "ticket_number", name="uq_tickets_org_ticket_number"
        ),
        sa.UniqueConstraint(
            "organization_id", "ticket_reference", name="uq_tickets_org_ticket_reference"
        ),
        sa.CheckConstraint("ticket_number > 0", name=op.f("ck_tickets_ticket_number_positive")),
        sa.CheckConstraint(
            "status IN ('open', 'pending', 'in_progress', 'resolved', 'closed')",
            name=op.f("ck_tickets_valid_status"),
        ),
        sa.CheckConstraint(
            "priority IN ('urgent', 'high', 'medium', 'low')",
            name=op.f("ck_tickets_valid_priority"),
        ),
        sa.CheckConstraint(
            "channel IN ('email', 'chat', 'api', 'web', 'internal')",
            name=op.f("ck_tickets_valid_channel"),
        ),
    )
    op.create_index(
        op.f("ix_tickets_organization_id"), "tickets", ["organization_id"], unique=False
    )
    op.create_index(op.f("ix_tickets_customer_id"), "tickets", ["customer_id"], unique=False)
    op.create_index(
        op.f("ix_tickets_assigned_actor_id"),
        "tickets",
        ["assigned_actor_id"],
        unique=False,
    )
    op.create_index("ix_tickets_org_status", "tickets", ["organization_id", "status"], unique=False)
    op.create_index(
        "ix_tickets_org_priority",
        "tickets",
        ["organization_id", "priority"],
        unique=False,
    )
    op.create_index(
        "ix_tickets_org_created_at",
        "tickets",
        ["organization_id", "created_at"],
        unique=False,
    )

    # 6. Conversations table
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope for this conversation thread",
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Parent support ticket for this thread",
        ),
        sa.Column(
            "channel_type",
            sa.String(length=30),
            server_default="email",
            nullable=False,
            comment="Channel medium for this specific thread",
        ),
        sa.Column(
            "external_thread_id",
            sa.String(length=255),
            nullable=True,
            comment="External thread identifier for deduplication and grouping",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
            comment="Thread lifecycle status",
        ),
        sa.Column(
            "last_message_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of latest message appended to this thread",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Structured metadata associated with the conversation thread",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_conversations_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_conversations_ticket_org",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.UniqueConstraint("id", "organization_id", name="uq_conversations_id_organization_id"),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'archived', 'closed')",
            name=op.f("ck_conversations_valid_status"),
        ),
        sa.CheckConstraint(
            "channel_type IN ('email', 'chat', 'api', 'web', 'internal')",
            name=op.f("ck_conversations_valid_channel_type"),
        ),
    )
    op.create_index(
        op.f("ix_conversations_organization_id"),
        "conversations",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversations_ticket_id"), "conversations", ["ticket_id"], unique=False
    )
    op.create_index(
        "ix_conversations_org_ticket",
        "conversations",
        ["organization_id", "ticket_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_org_external_thread",
        "conversations",
        ["organization_id", "external_thread_id"],
        unique=False,
    )

    # 7. Messages table
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization owning this message",
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Conversation thread containing this message",
        ),
        sa.Column(
            "direction",
            sa.String(length=20),
            nullable=False,
            comment="Message transmission direction (inbound, outbound)",
        ),
        sa.Column(
            "author_type",
            sa.String(length=20),
            nullable=False,
            comment="Author category (customer, agent, system, ai)",
        ),
        sa.Column(
            "author_id",
            sa.String(length=100),
            nullable=True,
            comment="Author identifier",
        ),
        sa.Column(
            "sender_display_name",
            sa.String(length=255),
            nullable=True,
            comment="Display name of the message sender",
        ),
        sa.Column(
            "body_text",
            sa.Text(),
            nullable=False,
            comment="Plain text message body content",
        ),
        sa.Column(
            "body_rich",
            sa.JSON(),
            nullable=True,
            comment="Optional structured or formatted rich payload",
        ),
        sa.Column(
            "content_type",
            sa.String(length=50),
            server_default="text/plain",
            nullable=False,
            comment="MIME content type of the primary body",
        ),
        sa.Column(
            "external_message_id",
            sa.String(length=255),
            nullable=True,
            comment="Provider or protocol message identifier for idempotency",
        ),
        sa.Column(
            "sequence_number",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Deterministic secondary sequence ordering key within thread",
        ),
        sa.Column(
            "delivery_status",
            sa.String(length=30),
            server_default="received",
            nullable=False,
            comment="Delivery lifecycle status",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "provider_sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Upstream provider timestamp",
        ),
        sa.Column(
            "metadata",
            sa.JSON(),
            nullable=True,
            comment="Structured metadata associated with the message",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_messages_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["conversations.id", "conversations.organization_id"],
            name="fk_messages_conversation_org",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("id", "organization_id", name="uq_messages_id_organization_id"),
        sa.CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name=op.f("ck_messages_valid_direction"),
        ),
        sa.CheckConstraint(
            "author_type IN ('customer', 'agent', 'system', 'ai')",
            name=op.f("ck_messages_valid_author_type"),
        ),
        sa.CheckConstraint("sequence_number >= 0", name=op.f("ck_messages_sequence_nonnegative")),
    )
    op.create_index(
        op.f("ix_messages_organization_id"), "messages", ["organization_id"], unique=False
    )
    op.create_index(
        op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False
    )
    op.create_index(
        "ix_messages_thread_order",
        "messages",
        ["conversation_id", "created_at", "sequence_number"],
        unique=False,
    )
    op.create_index(
        "ix_messages_org_external_msg_id",
        "messages",
        ["organization_id", "external_message_id"],
        unique=False,
    )

    # 8. Attachments table
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope for this attachment",
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Parent message containing this attachment",
        ),
        sa.Column(
            "filename",
            sa.String(length=255),
            nullable=False,
            comment="Sanitized original filename as uploaded by client",
        ),
        sa.Column(
            "storage_key",
            sa.String(length=500),
            nullable=False,
            comment="Opaque internal object-storage locator key",
        ),
        sa.Column(
            "content_type",
            sa.String(length=100),
            nullable=False,
            comment="MIME media type",
        ),
        sa.Column(
            "size_bytes",
            sa.BigInteger(),
            nullable=False,
            comment="File size in bytes",
        ),
        sa.Column(
            "checksum_sha256",
            sa.String(length=64),
            nullable=True,
            comment="Hex-encoded SHA-256 digest of stored bytes",
        ),
        sa.Column(
            "scan_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
            comment="Antivirus / malware scan and readiness status",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_attachments_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["message_id", "organization_id"],
            ["messages.id", "messages.organization_id"],
            name="fk_attachments_message_org",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_attachments_storage_key")),
        sa.CheckConstraint("size_bytes >= 0", name=op.f("ck_attachments_size_nonnegative")),
        sa.CheckConstraint(
            "scan_status IN ('pending', 'scanned_clean', 'infected', 'quarantined', 'ready')",
            name=op.f("ck_attachments_valid_scan_status"),
        ),
    )
    op.create_index(
        op.f("ix_attachments_organization_id"),
        "attachments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attachments_message_id"),
        "attachments",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        "ix_attachments_org_message",
        "attachments",
        ["organization_id", "message_id"],
        unique=False,
    )

    # 9. Ticket Events table
    op.create_table(
        "ticket_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope for this lifecycle event",
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Ticket subject of the lifecycle event",
        ),
        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
            comment="Domain event category",
        ),
        sa.Column(
            "event_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="UTC timestamp when the event occurred",
        ),
        sa.Column(
            "actor_type",
            sa.String(length=20),
            server_default="system",
            nullable=False,
            comment="Actor initiating the mutation",
        ),
        sa.Column(
            "actor_id",
            sa.String(length=100),
            nullable=True,
            comment="Identifier of the executing actor",
        ),
        sa.Column(
            "previous_value",
            sa.JSON(),
            nullable=True,
            comment="State representation prior to mutation",
        ),
        sa.Column(
            "new_value",
            sa.JSON(),
            nullable=True,
            comment="State representation subsequent to mutation",
        ),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=True,
            comment="Contextual structured payload explaining the event",
        ),
        sa.Column(
            "correlation_id",
            sa.String(length=100),
            nullable=True,
            comment="Request correlation ID linking the mutation to an HTTP trace",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_ticket_events_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_ticket_events_ticket_org",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_events")),
        sa.CheckConstraint(
            "actor_type IN ('customer', 'agent', 'system', 'ai')",
            name=op.f("ck_ticket_events_valid_actor_type"),
        ),
    )
    op.create_index(
        op.f("ix_ticket_events_organization_id"),
        "ticket_events",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ticket_events_ticket_id"),
        "ticket_events",
        ["ticket_id"],
        unique=False,
    )
    op.create_index(
        "ix_ticket_events_ticket_order",
        "ticket_events",
        ["ticket_id", "event_timestamp"],
        unique=False,
    )

    # 10. Ingestion Receipts table
    op.create_table(
        "ingestion_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope for this ingestion event",
        ),
        sa.Column(
            "source_provider",
            sa.String(length=50),
            nullable=False,
            comment="Provider or protocol source",
        ),
        sa.Column(
            "external_event_id",
            sa.String(length=255),
            nullable=False,
            comment="External event identifier supplied by provider for deduplication",
        ),
        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
            comment="Category of event",
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="received",
            nullable=False,
            comment="Idempotency processing state",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="UTC timestamp when the inbound event was registered",
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp when processing completed",
        ),
        sa.Column(
            "error_code",
            sa.String(length=50),
            nullable=True,
            comment="Sanitized error classification code if processing failed",
        ),
        sa.Column(
            "error_summary",
            sa.String(length=255),
            nullable=True,
            comment="High-level non-sensitive summary of ingestion failure",
        ),
        sa.Column(
            "correlation_id",
            sa.String(length=100),
            nullable=True,
            comment="Request correlation ID linking ingestion to gateway telemetry",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_ingestion_receipts_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_receipts")),
        sa.UniqueConstraint(
            "organization_id",
            "source_provider",
            "external_event_id",
            name="uq_ingestion_receipts_provider_event",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'processing', 'processed', 'duplicate', 'failed', 'ignored')",
            name=op.f("ck_ingestion_receipts_valid_status"),
        ),
    )
    op.create_index(
        op.f("ix_ingestion_receipts_organization_id"),
        "ingestion_receipts",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_ingestion_receipts_org_status",
        "ingestion_receipts",
        ["organization_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    # Drop tables in exact reverse dependency order
    op.drop_table("ingestion_receipts")
    op.drop_table("ticket_events")
    op.drop_table("attachments")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("tickets")
    op.drop_table("customer_identities")
    op.drop_table("customers")
    op.drop_table("organization_ticket_counters")
    op.drop_table("organizations")
