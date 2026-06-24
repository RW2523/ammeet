"""Per-workspace calendar auto-join opt-in + dedup index for synced meetings

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Explicit per-workspace consent for the background calendar auto-join sweep.
    op.add_column(
        "workspaces",
        sa.Column(
            "calendar_auto_join_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Atomic dedup: one synced meeting per (workspace, calendar event).
    op.create_index(
        "uq_meetings_workspace_calendar_event",
        "meetings",
        ["workspace_id", "calendar_event_id"],
        unique=True,
        postgresql_where=sa.text("calendar_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_meetings_workspace_calendar_event", table_name="meetings")
    op.drop_column("workspaces", "calendar_auto_join_enabled")
