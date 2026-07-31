"""Action item kind — distinguish the owner's commitments from tasks assigned to others

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "action_items",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="action"),
    )


def downgrade() -> None:
    op.drop_column("action_items", "kind")
