"""Initial foundational schema and system event audit log.

Revision ID: 0001_initial_foundation
Revises: None
Create Date: 2026-10-14 09:50:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create system_event_logs table
    op.create_table(
        "system_event_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "event_name",
            sa.String(length=100),
            nullable=False,
            comment="Machine-readable system event identifier",
        ),
        sa.Column(
            "component",
            sa.String(length=50),
            nullable=False,
            comment="Platform component emitting the event",
        ),
        sa.Column(
            "payload",
            sa.JSON(),
            nullable=True,
            comment="Structured metadata associated with the event",
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
    )

    # Create explicit naming-convention indexes
    op.create_index(
        op.f("ix_system_event_logs_event_name"),
        "system_event_logs",
        ["event_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_event_logs_component"),
        "system_event_logs",
        ["component"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_system_event_logs_component"), table_name="system_event_logs")
    op.drop_index(op.f("ix_system_event_logs_event_name"), table_name="system_event_logs")
    op.drop_table("system_event_logs")
