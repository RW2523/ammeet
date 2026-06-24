"""Add llm_config table for runtime LLM provider selection

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False, server_default="openai"),
        sa.Column("model", sa.String(120), nullable=False, server_default="gpt-4o"),
        sa.Column("embedding_model", sa.String(120), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_config")
