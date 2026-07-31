"""Interactive delegate — approval requests + wider stage column

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # "interactive" no longer fits the original 10-char stage column
    op.alter_column("delegate_sessions", "stage", type_=sa.String(length=20))
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "delegate_session_id",
            sa.String(length=36),
            sa.ForeignKey("delegate_sessions.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("meeting_id", sa.String(length=36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), index=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), index=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("proposed_answer", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="pending"),
        sa.Column("decided_by_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="web"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.alter_column("delegate_sessions", "stage", type_=sa.String(length=10))
