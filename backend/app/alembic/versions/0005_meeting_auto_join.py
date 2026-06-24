"""Add meeting auto-join columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("auto_join_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "meetings",
        sa.Column("auto_join_dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meetings", "auto_join_dispatched_at")
    op.drop_column("meetings", "auto_join_enabled")
