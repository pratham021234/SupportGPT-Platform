"""Event ingestion subsystem: event_sources table, receipts expansion, and tenant RLS.

Revision ID: 0005_event_ingestion_subsystem
Revises: 0004_ticket_concurrency_version
Create Date: 2026-10-14 13:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_event_ingestion_subsystem"
down_revision: str | None = "0004_ticket_concurrency_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Create event_sources table
    op.create_table(
        "event_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Organization scope for this external source",
        ),
        sa.Column(
            "provider",
            sa.String(length=50),
            server_default="generic_webhook",
            nullable=False,
            comment="Provider type (generic_webhook, custom_api, email_postmark, etc.)",
        ),
        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
            comment="Human-readable label for this integration source",
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="active",
            nullable=False,
            comment="Source connection state (active, inactive, revoked)",
        ),
        sa.Column(
            "external_account_id",
            sa.String(length=255),
            nullable=True,
            comment="External installation, project, or account ID",
        ),
        sa.Column(
            "signing_secret_hash",
            sa.String(length=255),
            nullable=False,
            comment="Cryptographic hash of the signing secret for integrity verification",
        ),
        sa.Column(
            "signing_secret_encrypted",
            sa.Text(),
            nullable=True,
            comment="Encrypted signing secret ciphertext stored securely at rest",
        ),
        sa.Column(
            "secret_reference",
            sa.String(length=255),
            nullable=True,
            comment="Managed secret reference URI (e.g. env:WH_SEC or vault:path)",
        ),
        sa.Column(
            "signing_secret_preview",
            sa.String(length=30),
            nullable=True,
            comment="Masked preview of the secret for operator display",
        ),
        sa.Column(
            "supported_event_types",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(),
            server_default='["ticket.created", "ticket.updated", "message.received"]',
            nullable=False,
            comment="JSON array of event types allowed for this source",
        ),
        sa.Column(
            "last_event_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp of the most recent event received from this source",
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
            name=op.f("fk_event_sources_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_sources")),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'revoked')",
            name=op.f("ck_event_sources_valid_status"),
        ),
    )
    op.create_index(
        op.f("ix_event_sources_organization_id"),
        "event_sources",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_event_sources_org_provider",
        "event_sources",
        ["organization_id", "provider"],
        unique=False,
    )

    # 2. Expand ingestion_receipts table
    op.add_column(
        "ingestion_receipts",
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Foreign key to the event source configuration if originating from a registered source",
        ),
    )
    op.add_column(
        "ingestion_receipts",
        sa.Column(
            "payload_digest",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hex digest of the raw inbound event payload",
        ),
    )
    op.add_column(
        "ingestion_receipts",
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.Text(),
            nullable=True,
            comment="Parsed or normalized payload necessary for asynchronous domain processing",
        ),
    )
    op.add_column(
        "ingestion_receipts",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Number of worker processing attempts",
        ),
    )
    op.add_column(
        "ingestion_receipts",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Earliest UTC timestamp for the next worker processing attempt",
        ),
    )
    op.add_column(
        "ingestion_receipts",
        sa.Column(
            "processing_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp when the current worker lease started",
        ),
    )
    op.add_column(
        "ingestion_receipts",
        sa.Column(
            "locked_by",
            sa.String(length=100),
            nullable=True,
            comment="Worker instance identifier holding the processing lease",
        ),
    )
    op.add_column(
        "ingestion_receipts",
        sa.Column(
            "schema_version",
            sa.String(length=20),
            server_default="1.0",
            nullable=False,
            comment="Canonical event schema version",
        ),
    )

    op.create_foreign_key(
        op.f("fk_ingestion_receipts_source_id_event_sources"),
        "ingestion_receipts",
        "event_sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_ingestion_receipts_source_id"),
        "ingestion_receipts",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        "ix_ingestion_receipts_queue",
        "ingestion_receipts",
        ["status", "next_attempt_at"],
        unique=False,
    )

    # 3. Update check constraint for status on ingestion_receipts
    if is_postgres:
        op.execute(
            "ALTER TABLE ingestion_receipts DROP CONSTRAINT IF EXISTS ck_ingestion_receipts_valid_status;"
        )
        op.execute(
            """
            ALTER TABLE ingestion_receipts ADD CONSTRAINT ck_ingestion_receipts_valid_status
            CHECK (status IN ('received', 'queued', 'processing', 'retry_wait', 'processed', 'dead_letter', 'quarantined', 'duplicate', 'failed', 'ignored'));
            """
        )

        # 4. PostgreSQL Row-Level Security (RLS) policies
        for table in ["event_sources", "ingestion_receipts"]:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                FOR ALL
                USING (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid
                    OR current_setting('app.is_system_admin', true) = 'true'
                );
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        for table in ["event_sources", "ingestion_receipts"]:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

        op.execute(
            "ALTER TABLE ingestion_receipts DROP CONSTRAINT IF EXISTS ck_ingestion_receipts_valid_status;"
        )
        op.execute(
            """
            ALTER TABLE ingestion_receipts ADD CONSTRAINT ck_ingestion_receipts_valid_status
            CHECK (status IN ('received', 'processing', 'processed', 'duplicate', 'failed', 'ignored'));
            """
        )

    op.drop_index("ix_ingestion_receipts_queue", table_name="ingestion_receipts")
    op.drop_index(op.f("ix_ingestion_receipts_source_id"), table_name="ingestion_receipts")
    op.drop_constraint(
        op.f("fk_ingestion_receipts_source_id_event_sources"),
        "ingestion_receipts",
        type_="foreignkey",
    )

    op.drop_column("ingestion_receipts", "schema_version")
    op.drop_column("ingestion_receipts", "locked_by")
    op.drop_column("ingestion_receipts", "processing_started_at")
    op.drop_column("ingestion_receipts", "next_attempt_at")
    op.drop_column("ingestion_receipts", "attempt_count")
    op.drop_column("ingestion_receipts", "payload")
    op.drop_column("ingestion_receipts", "payload_digest")
    op.drop_column("ingestion_receipts", "source_id")

    op.drop_index("ix_event_sources_org_provider", table_name="event_sources")
    op.drop_index(op.f("ix_event_sources_organization_id"), table_name="event_sources")
    op.drop_table("event_sources")
