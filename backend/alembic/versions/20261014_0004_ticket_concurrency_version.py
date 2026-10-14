"""Add optimistic concurrency lock version to tickets.

Revision ID: 0004_ticket_concurrency_version
Revises: 0003_auth_membership_rbac
Create Date: 2026-10-14 12:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_ticket_concurrency_version"
down_revision: str | None = "0003_auth_membership_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add lock_version column to tickets table for optimistic concurrency control."""
    op.add_column(
        "tickets",
        sa.Column(
            "lock_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
            comment="Optimistic concurrency control lock version counter",
        ),
    )


def downgrade() -> None:
    """Remove lock_version column from tickets table."""
    op.drop_column("tickets", "lock_version")
