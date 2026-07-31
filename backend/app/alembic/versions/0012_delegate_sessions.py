"""Delegate sessions — Phase 3 stages A (silent) and B (briefed)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delegate_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("meeting_id", sa.String(length=36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), index=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), index=True),
        sa.Column("stage", sa.String(length=10), nullable=False, server_default="silent"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="created"),
        sa.Column("bot_id", sa.String(length=256), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disclosure_logged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("script_json", sa.Text(), nullable=True),
        sa.Column("follow_ups_json", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("delegate_sessions")
