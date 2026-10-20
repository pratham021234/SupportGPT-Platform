"""Authentication, organization membership, and tenant RLS security foundation.

Revision ID: 0003_auth_membership_rbac
Revises: 0002_canonical_domain_model
Create Date: 2026-10-14 11:30:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_auth_membership_rbac"
down_revision: str | None = "0002_canonical_domain_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_RLS_TABLES = [
    "tickets",
    "conversations",
    "messages",
    "attachments",
    "ticket_events",
    "customers",
    "customer_identities",
]


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'disabled')",
            name="ck_users_valid_status",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_status", "users", ["status"])

    # 2. Organization Memberships table
    op.create_table(
        "organization_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(30), server_default="agent", nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_memberships_org_user"
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'agent', 'viewer')",
            name="ck_organization_memberships_valid_role",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'invited', 'revoked')",
            name="ck_organization_memberships_valid_status",
        ),
    )
    op.create_index(
        "ix_organization_memberships_org_id", "organization_memberships", ["organization_id"]
    )
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    op.create_index("ix_organization_memberships_role", "organization_memberships", ["role"])
    op.create_index("ix_organization_memberships_status", "organization_memberships", ["status"])

    # 3. User Sessions table
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_token_hash", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index(
        "ix_user_sessions_token_hash", "user_sessions", ["session_token_hash"], unique=True
    )
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    # 4. PostgreSQL Row-Level Security (RLS) policies
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TENANT_RLS_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_isolation ON {table}
                FOR ALL
                USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid);
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TENANT_RLS_TABLES:
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Drop tables in reverse foreign-key dependency order
    op.drop_table("user_sessions")
    op.drop_table("organization_memberships")
    op.drop_table("users")
