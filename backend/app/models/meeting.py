from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import _now, _uuid


class MeetingMode(str, Enum):
    SHADOW = "shadow"
    LIVE_NAVIGATOR = "live_navigator"
    PROXY = "proxy"
    DATA_COLLECTION = "data_collection"


class MeetingStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CaptureLevel(int, Enum):
    SUMMARY_ONLY = 1
    TRANSCRIPT_AND_SUMMARY = 2


class Person(Base):
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_authority: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[MeetingMode] = mapped_column(String(30), default=MeetingMode.SHADOW)
    status: Mapped[MeetingStatus] = mapped_column(String(30), default=MeetingStatus.DRAFT)
    capture_level: Mapped[int] = mapped_column(Integer, default=CaptureLevel.TRANSCRIPT_AND_SUMMARY)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Proxy specific
    proxy_consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    proxy_intro_logged: Mapped[bool] = mapped_column(Boolean, default=False)
    # Calendar integration ref
    calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    context_sources: Mapped[list[ContextSource]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    questions: Mapped[list[Question]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    answers: Mapped[list[Answer]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    action_items: Mapped[list[ActionItem]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    decisions: Mapped[list[Decision]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    risks: Mapped[list[Risk]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    reports: Mapped[list[Report]] = relationship(back_populates="meeting", cascade="all, delete-orphan")


class ContextSource(Base):
    __tablename__ = "context_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    source_type: Mapped[str] = mapped_column(String(50))  # upload | jira | calendar | manual
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|processing|done|failed
    extracted_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    meeting: Mapped[Meeting] = relationship(back_populates="context_sources")


class QuestionPriority(str, Enum):
    MUST_ASK = "must_ask"
    IF_TIME = "if_time"
    ASK_LATER = "ask_later"
    ANSWERED = "answered"
    NEEDS_HUMAN = "needs_human"


class QuestionCategory(str, Enum):
    STATUS = "status"
    BLOCKER = "blocker"
    OWNERSHIP = "ownership"
    DEADLINE = "deadline"
    CLIENT = "client"
    DECISION = "decision"
    RISK = "risk"
    GENERAL = "general"


class QuestionStatus(str, Enum):
    PENDING = "pending"
    ASKED = "asked"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    ESCALATED = "escalated"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[QuestionCategory] = mapped_column(String(30), default=QuestionCategory.GENERAL)
    priority: Mapped[QuestionPriority] = mapped_column(String(30), default=QuestionPriority.MUST_ASK)
    status: Mapped[QuestionStatus] = mapped_column(String(30), default=QuestionStatus.PENDING)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Mode flags
    proxy_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    human_only: Mapped[bool] = mapped_column(Boolean, default=False)
    do_not_ask: Mapped[bool] = mapped_column(Boolean, default=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Source reference
    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    meeting: Mapped[Meeting] = relationship(back_populates="questions")
    answers: Mapped[list[Answer]] = relationship(back_populates="question")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"), nullable=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    speaker: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    meeting: Mapped[Meeting] = relationship(back_populates="answers")
    question: Mapped[Question | None] = relationship(back_populates="answers")


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open")
    jira_ticket_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    meeting: Mapped[Meeting] = relationship(back_populates="action_items")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    made_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    meeting: Mapped[Meeting] = relationship(back_populates="decisions")


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    meeting: Mapped[Meeting] = relationship(back_populates="risks")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full structured JSON
    slack_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    jira_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Export states – require explicit user review
    slack_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    jira_updated: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    meeting: Mapped[Meeting] = relationship(back_populates="reports")
