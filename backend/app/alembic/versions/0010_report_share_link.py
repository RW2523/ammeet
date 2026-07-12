"""Report public share link — opaque token for a read-only recap

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("share_token", sa.String(length=48), nullable=True))
    op.add_column("reports", sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_reports_share_token", "reports", ["share_token"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_reports_share_token", table_name="reports")
    op.drop_column("reports", "shared_at")
    op.drop_column("reports", "share_token")
