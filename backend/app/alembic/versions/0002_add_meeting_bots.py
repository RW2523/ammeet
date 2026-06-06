"""Add meeting_bots table and meeting_url column.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add meeting_url to meetings table
    op.add_column(
        "meetings",
        sa.Column("meeting_url", sa.Text(), nullable=True),
    )

    # Create meeting_bots table
    op.create_table(
        "meeting_bots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("external_bot_id", sa.String(256), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False, server_default="mock"),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("meeting_url", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(36), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("transcript_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_meeting_bots_meeting_id", "meeting_bots", ["meeting_id"])
    op.create_index("ix_meeting_bots_workspace_id", "meeting_bots", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_meeting_bots_workspace_id", "meeting_bots")
    op.drop_index("ix_meeting_bots_meeting_id", "meeting_bots")
    op.drop_table("meeting_bots")
    op.drop_column("meetings", "meeting_url")
