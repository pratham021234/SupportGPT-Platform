"""Response verification, policy enforcement, approval workflow, and tenant RLS.

Revision ID: 0007_response_verification_and_approval
Revises: 0006_knowledge_base_subsystem
Create Date: 2026-10-20 21:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_response_verification"
down_revision: str | None = "0006_knowledge_base_subsystem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Create response_drafts table
    op.create_table(
        "response_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            index=True,
        ),
        sa.Column("original_query", sa.Text(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "lifecycle_status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
            index=True,
        ),
        sa.Column(
            "evidence_references",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_postgres else "[]",
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("version_number >= 1", name="ck_response_drafts_version_positive"),
        sa.CheckConstraint("length(draft_text) > 0", name="ck_response_drafts_text_nonempty"),
        sa.ForeignKeyConstraint(
            ["ticket_id", "organization_id"],
            ["tickets.id", "tickets.organization_id"],
            name="fk_response_drafts_ticket_tenant",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id"],
            ["conversations.id", "conversations.organization_id"],
            name="fk_response_drafts_conversation_tenant",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_response_drafts_org_status",
        "response_drafts",
        ["organization_id", "lifecycle_status"],
    )
    op.create_index(
        "ix_response_drafts_org_ticket",
        "response_drafts",
        ["organization_id", "ticket_id"],
    )

    # 2. Create verification_runs table
    op.create_table(
        "verification_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("response_drafts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column(
            "verification_pipeline_version",
            sa.String(length=32),
            nullable=False,
            server_default="v1.0.0",
        ),
        sa.Column("policy_set_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="passed", index=True
        ),
        sa.Column(
            "risk_level", sa.String(length=32), nullable=False, server_default="low", index=True
        ),
        sa.Column("requires_human_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "machine_readable_findings",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if is_postgres else "{}",
        ),
        sa.Column(
            "evidence_references",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_postgres else "[]",
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_verification_runs_org_draft_version",
        "verification_runs",
        ["organization_id", "draft_id", "draft_version"],
    )
    op.create_index(
        "ix_verification_runs_org_status",
        "verification_runs",
        ["organization_id", "status"],
    )

    # 3. Create claim_findings table
    op.create_table(
        "claim_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "verification_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verification_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("claim_category", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column(
            "support_status",
            sa.String(length=32),
            nullable=False,
            server_default="supported",
            index=True,
        ),
        sa.Column(
            "evidence_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_postgres else "[]",
        ),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "verification_method",
            sa.String(length=32),
            nullable=False,
            server_default="evidence_grounding",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_claim_findings_run_status",
        "claim_findings",
        ["verification_run_id", "support_status"],
    )
    op.create_index(
        "ix_claim_findings_org_category",
        "claim_findings",
        ["organization_id", "claim_category"],
    )

    # 4. Create policy_rules table
    op.create_table(
        "policy_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "policy_category",
            sa.String(length=32),
            nullable=False,
            server_default="factual_grounding",
            index=True,
        ),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="high"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true", index=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "rule_type",
            sa.String(length=64),
            nullable=False,
            server_default="unsupported_claim_block",
        ),
        sa.Column(
            "rule_config",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if is_postgres else "{}",
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("version_number >= 1", name="ck_policy_rules_version_positive"),
        sa.UniqueConstraint("organization_id", "name", name="uq_policy_rules_org_name"),
    )
    op.create_index(
        "ix_policy_rules_org_enabled",
        "policy_rules",
        ["organization_id", "is_enabled"],
    )

    # 5. Create approval_requests table
    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "draft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("response_drafts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column(
            "verification_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("verification_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="pending", index=True
        ),
        sa.Column("required_role", sa.String(length=32), nullable=False, server_default="agent"),
        sa.Column("separation_of_duties", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "decision_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_approval_requests_org_status",
        "approval_requests",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_approval_requests_org_draft_version",
        "approval_requests",
        ["organization_id", "draft_id", "draft_version"],
    )

    # 6. Create verification_audit_events table
    op.create_table(
        "verification_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("event_summary", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if is_postgres else "{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )
    op.create_index(
        "ix_verification_audit_org_event",
        "verification_audit_events",
        ["organization_id", "event_type"],
    )
    op.create_index(
        "ix_verification_audit_org_entity",
        "verification_audit_events",
        ["organization_id", "entity_type", "entity_id"],
    )

    # 7. Apply PostgreSQL Row-Level Security (RLS) policies
    if is_postgres:
        tables = [
            "response_drafts",
            "verification_runs",
            "claim_findings",
            "policy_rules",
            "approval_requests",
            "verification_audit_events",
        ]
        for tbl in tables:
            op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
            op.execute(
                f"""
                CREATE POLICY {tbl}_tenant_isolation ON {tbl}
                FOR ALL
                USING (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid
                    OR current_setting('app.is_system_admin', true) = 'true'
                )
                WITH CHECK (
                    organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid
                    OR current_setting('app.is_system_admin', true) = 'true'
                );
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    tables = [
        "verification_audit_events",
        "approval_requests",
        "claim_findings",
        "policy_rules",
        "verification_runs",
        "response_drafts",
    ]

    if is_postgres:
        for tbl in tables:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation_policy ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    for tbl in tables:
        op.drop_table(tbl)
