# single source of truth revision
"""Initial schema"""
# Revision ID: 0001
# Revises: 
# Create Date: 2026-06-06

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_superuser", sa.Boolean, default=False),
        sa.Column("totp_secret", sa.String(64), nullable=True),
        sa.Column("totp_enabled", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"])

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(20), default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "people",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("responsibility", sa.Text, nullable=True),
        sa.Column("current_work", sa.Text, nullable=True),
        sa.Column("decision_authority", sa.Text, nullable=True),
        sa.Column("follow_up", sa.Text, nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("is_external", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_people_workspace_id", "people", ["workspace_id"])

    op.create_table(
        "meetings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("purpose", sa.Text, nullable=True),
        sa.Column("mode", sa.String(30), default="shadow"),
        sa.Column("status", sa.String(30), default="draft"),
        sa.Column("capture_level", sa.Integer, default=2),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proxy_consent_given", sa.Boolean, default=False),
        sa.Column("proxy_intro_logged", sa.Boolean, default=False),
        sa.Column("calendar_event_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_meetings_workspace_id", "meetings", ["workspace_id"])

    op.create_table(
        "context_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("source_type", sa.String(50)),
        sa.Column("filename", sa.String(500), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("extraction_status", sa.String(30), default="pending"),
        sa.Column("extracted_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("category", sa.String(30), default="general"),
        sa.Column("priority", sa.String(30), default="must_ask"),
        sa.Column("status", sa.String(30), default="pending"),
        sa.Column("sort_order", sa.Integer, default=0),
        sa.Column("proxy_allowed", sa.Boolean, default=False),
        sa.Column("human_only", sa.Boolean, default=False),
        sa.Column("do_not_ask", sa.Boolean, default=False),
        sa.Column("is_private", sa.Boolean, default=False),
        sa.Column("escalation_rule", sa.String(100), nullable=True),
        sa.Column("source_context", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_questions_meeting_id", "questions", ["meeting_id"])

    op.create_table(
        "answers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("question_id", sa.String(36), sa.ForeignKey("questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("speaker", sa.String(255), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("is_complete", sa.Boolean, default=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "action_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("deadline", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), default="open"),
        sa.Column("jira_ticket_ref", sa.String(100), nullable=True),
        sa.Column("source_context", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("made_by", sa.String(255), nullable=True),
        sa.Column("requires_approval", sa.Boolean, default=False),
        sa.Column("approved", sa.Boolean, nullable=True),
        sa.Column("source_context", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "risks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("severity", sa.String(20), default="medium"),
        sa.Column("escalated", sa.Boolean, default=False),
        sa.Column("source_context", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("full_json", sa.Text, nullable=True),
        sa.Column("slack_draft", sa.Text, nullable=True),
        sa.Column("email_draft", sa.Text, nullable=True),
        sa.Column("jira_draft", sa.Text, nullable=True),
        sa.Column("slack_sent", sa.Boolean, default=False),
        sa.Column("email_sent", sa.Boolean, default=False),
        sa.Column("jira_updated", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("meeting_id", sa.String(36), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, default=0),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("embedding", sa.Text, nullable=True),  # stored as text; pgvector handles natively after extension
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_knowledge_chunks_workspace_id", "knowledge_chunks", ["workspace_id"])

    op.create_table(
        "integrations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), default="disconnected"),
        sa.Column("encrypted_token", sa.Text, nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.Text, nullable=True),
        sa.Column("config_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_integrations_workspace_id", "integrations", ["workspace_id"])

    op.create_table(
        "retention_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, unique=True),
        sa.Column("audio_retention_days", sa.Integer, default=7),
        sa.Column("transcript_retention_days", sa.Integer, default=90),
        sa.Column("summary_retention_days", sa.Integer, default=365),
        sa.Column("action_item_retention_days", sa.Integer, default=730),
        sa.Column("sensitive_do_not_store", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("retention_policies")
    op.drop_table("integrations")
    op.drop_table("knowledge_chunks")
    op.drop_table("reports")
    op.drop_table("risks")
    op.drop_table("decisions")
    op.drop_table("action_items")
    op.drop_table("answers")
    op.drop_table("questions")
    op.drop_table("context_sources")
    op.drop_table("meetings")
    op.drop_table("people")
    op.drop_table("audit_logs")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
    op.drop_table("users")
