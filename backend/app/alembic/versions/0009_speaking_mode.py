"""Speak Mode — speaking points + participant responses

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "speaking_points",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("meeting_id", sa.String(length=36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), index=True),
        sa.Column("workspace_id", sa.String(length=36), index=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False, server_default="Main"),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="should"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="pending"),
        sa.Column("covered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("covered_by_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "speaking_responses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("meeting_id", sa.String(length=36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), index=True),
        sa.Column("workspace_id", sa.String(length=36), index=True),
        sa.Column("point_id", sa.String(length=36), sa.ForeignKey("speaking_points.id", ondelete="SET NULL"), nullable=True),
        sa.Column("speaker", sa.String(length=120), nullable=False, server_default="Participant"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="response"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("speaking_responses")
    op.drop_table("speaking_points")
