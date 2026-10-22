"""AI Observability, Execution Traces, Failure Investigations, Evaluation Runs, and Token Usage.

Revision ID: 0008_ai_observability_and_evaluation
Revises: 0007_response_verification
Create Date: 2026-10-20 22:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_ai_observability"
down_revision: str | None = "0007_response_verification"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Create ai_operation_traces table
    op.create_table(
        "ai_operation_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("trace_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("request_id", sa.String(length=64), nullable=True, index=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("operation_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default="none"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column(
            "outcome", sa.String(length=32), nullable=False, server_default="success", index=True
        ),
        sa.Column("error_category", sa.String(length=64), nullable=True, index=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "token_usage",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if is_postgres else "{}",
        ),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("pipeline_version", sa.String(length=32), nullable=True),
        sa.Column("policy_version", sa.String(length=32), nullable=True),
        sa.Column(
            "spans",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_postgres else "[]",
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
        "ix_ai_operation_traces_org_created",
        "ai_operation_traces",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_ai_operation_traces_org_op_outcome",
        "ai_operation_traces",
        ["organization_id", "operation_type", "outcome"],
    )

    # 2. Create failure_investigations table
    op.create_table(
        "failure_investigations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "investigation_id", sa.String(length=32), nullable=False, unique=True, index=True
        ),
        sa.Column("fingerprint", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "failure_category",
            sa.String(length=64),
            nullable=False,
            server_default="unknown_error",
            index=True,
        ),
        sa.Column(
            "severity", sa.String(length=32), nullable=False, server_default="medium", index=True
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="open", index=True
        ),
        sa.Column("trace_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("sanitized_error_summary", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pipeline_version", sa.String(length=32), nullable=True),
        sa.Column(
            "diagnostic_hypotheses",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_postgres else "[]",
        ),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column(
            "assigned_to_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_failure_investigations_org_fingerprint",
        "failure_investigations",
        ["organization_id", "fingerprint"],
    )
    op.create_index(
        "ix_failure_investigations_org_status_severity",
        "failure_investigations",
        ["organization_id", "status", "severity"],
    )

    # 3. Create evaluation_runs table
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "dataset_id",
            sa.String(length=64),
            nullable=False,
            server_default="enterprise_eval_dataset_v1",
        ),
        sa.Column("dataset_version", sa.String(length=64), nullable=False, server_default="v1.0"),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answerable_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unanswerable_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("generation_provider", sa.String(length=64), nullable=True),
        sa.Column("generation_model", sa.String(length=128), nullable=True),
        sa.Column(
            "retrieval_config",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if is_postgres else "{}",
        ),
        sa.Column("verification_pipeline_version", sa.String(length=32), nullable=True),
        sa.Column("policy_version", sa.String(length=32), nullable=True),
        sa.Column("mean_recall_at_k", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("mean_reciprocal_rank", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("citation_validity_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("abstention_accuracy", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="completed", index=True
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "case_results",
            postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb") if is_postgres else "[]",
        ),
        sa.Column(
            "regressions",
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_evaluation_runs_org_created",
        "evaluation_runs",
        ["organization_id", "created_at"],
    )

    # 4. Create ai_token_usages table
    op.create_table(
        "ai_token_usages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("trace_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("operation_type", sa.String(length=64), nullable=False, index=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_provider_reported", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("pricing_tier", sa.String(length=64), nullable=False, server_default="standard"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )
    op.create_index(
        "ix_ai_token_usages_org_created",
        "ai_token_usages",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_ai_token_usages_org_provider_model",
        "ai_token_usages",
        ["organization_id", "provider", "model"],
    )

    # 5. Apply PostgreSQL Row-Level Security (RLS) policies
    if is_postgres:
        tables = [
            "ai_operation_traces",
            "failure_investigations",
            "evaluation_runs",
            "ai_token_usages",
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
        "ai_token_usages",
        "evaluation_runs",
        "failure_investigations",
        "ai_operation_traces",
    ]

    if is_postgres:
        for tbl in tables:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl};")
            op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

    for tbl in tables:
        op.drop_table(tbl)
