"""Billing columns, usage records, email verification

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users — email verification
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # workspaces — subscription/billing state
    op.add_column("workspaces", sa.Column("plan", sa.String(20), nullable=False, server_default="free"))
    op.add_column("workspaces", sa.Column("stripe_customer_id", sa.String(64), nullable=True))
    op.add_column("workspaces", sa.Column("stripe_subscription_id", sa.String(64), nullable=True))
    op.add_column("workspaces", sa.Column("subscription_status", sa.String(30), nullable=True))
    op.add_column("workspaces", sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True))

    # usage_records — monthly metered usage per workspace
    op.create_table(
        "usage_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric", sa.String(50), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_usage_records_workspace_id", "usage_records", ["workspace_id"])
    op.create_index(
        "ix_usage_records_unique_metric_period",
        "usage_records",
        ["workspace_id", "metric", "period"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_records_unique_metric_period", "usage_records")
    op.drop_index("ix_usage_records_workspace_id", "usage_records")
    op.drop_table("usage_records")
    op.drop_column("workspaces", "current_period_end")
    op.drop_column("workspaces", "subscription_status")
    op.drop_column("workspaces", "stripe_subscription_id")
    op.drop_column("workspaces", "stripe_customer_id")
    op.drop_column("workspaces", "plan")
    op.drop_column("users", "email_verified")
