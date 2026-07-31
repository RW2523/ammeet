from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import _now, _uuid


class DelegateStage(str, Enum):
    SILENT = "silent"            # stage A — joins, discloses, records; never speaks again
    BRIEFED = "briefed"          # stage B — + delivers the owner's scripted items, captures follow-ups
    INTERACTIVE = "interactive"  # stage C — + KB-grounded answers, each gated by human approval


class DelegateSessionStatus(str, Enum):
    CREATED = "created"
    JOINING = "joining"
    ACTIVE = "active"
    LEAVING = "leaving"
    DONE = "done"
    ERROR = "error"


class DelegateSession(Base):
    """One cloud-delegate ("attend when I'm absent") session for a meeting."""

    __tablename__ = "delegate_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(20), default=DelegateStage.SILENT.value)
    status: Mapped[str] = mapped_column(String(20), default=DelegateSessionStatus.CREATED.value)
    # External provider bot id (Recall / browser bot-worker / mock)
    bot_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disclosure_logged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Stage-B script composed at session start (updates from Speak points + approved questions)
    script_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Questions directed at the absent owner, captured for follow-up: [{"asker","text","ts"}]
    follow_ups_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    TIMEOUT = "timeout"


class ApprovalRequest(Base):
    """One human-approval gate for an interactive-delegate proposed answer.
    The delegate waits for a decision; no decision within the window = silence."""

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    delegate_session_id: Mapped[str] = mapped_column(
        ForeignKey("delegate_sessions.id", ondelete="CASCADE"), index=True
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_answer: Mapped[str] = mapped_column(Text, nullable=False)
    # KB chunk refs the proposed answer was grounded in: [{"chunk_id","source_type","meeting_id"}]
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default=ApprovalStatus.PENDING.value)
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), default="web")  # web | ntfy

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
