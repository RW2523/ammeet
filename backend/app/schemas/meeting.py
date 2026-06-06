from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.meeting import (
    CaptureLevel,
    MeetingMode,
    MeetingStatus,
    QuestionCategory,
    QuestionPriority,
    QuestionStatus,
)


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    purpose: str | None = None
    mode: MeetingMode = MeetingMode.SHADOW
    capture_level: int = CaptureLevel.TRANSCRIPT_AND_SUMMARY
    scheduled_at: datetime | None = None


class MeetingUpdate(BaseModel):
    title: str | None = None
    purpose: str | None = None
    mode: MeetingMode | None = None
    status: MeetingStatus | None = None
    capture_level: int | None = None
    scheduled_at: datetime | None = None
    proxy_consent_given: bool | None = None


class MeetingOut(BaseModel):
    id: str
    workspace_id: str
    title: str
    purpose: str | None
    mode: MeetingMode
    status: MeetingStatus
    capture_level: int
    scheduled_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    proxy_consent_given: bool
    proxy_intro_logged: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionCreate(BaseModel):
    text: str = Field(min_length=1)
    category: QuestionCategory = QuestionCategory.GENERAL
    priority: QuestionPriority = QuestionPriority.MUST_ASK
    proxy_allowed: bool = False
    human_only: bool = False
    do_not_ask: bool = False
    is_private: bool = False
    escalation_rule: str | None = None
    sort_order: int = 0


class QuestionUpdate(BaseModel):
    text: str | None = None
    category: QuestionCategory | None = None
    priority: QuestionPriority | None = None
    status: QuestionStatus | None = None
    proxy_allowed: bool | None = None
    human_only: bool | None = None
    do_not_ask: bool | None = None
    is_private: bool | None = None
    escalation_rule: str | None = None
    sort_order: int | None = None


class QuestionOut(BaseModel):
    id: str
    meeting_id: str
    workspace_id: str
    text: str
    category: QuestionCategory
    priority: QuestionPriority
    status: QuestionStatus
    sort_order: int
    proxy_allowed: bool
    human_only: bool
    do_not_ask: bool
    is_private: bool
    escalation_rule: str | None
    source_context: str | None
    confidence: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnswerCreate(BaseModel):
    question_id: str | None = None
    speaker: str | None = None
    text: str = Field(min_length=1)
    is_complete: bool = True
    confidence: float | None = None


class AnswerOut(BaseModel):
    id: str
    meeting_id: str
    question_id: str | None
    speaker: str | None
    text: str
    is_complete: bool
    confidence: float | None
    captured_at: datetime

    model_config = {"from_attributes": True}


class ActionItemOut(BaseModel):
    id: str
    meeting_id: str
    workspace_id: str
    title: str
    owner: str | None
    deadline: str | None
    status: str
    jira_ticket_ref: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DecisionOut(BaseModel):
    id: str
    meeting_id: str
    text: str
    made_by: str | None
    requires_approval: bool
    approved: bool | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskOut(BaseModel):
    id: str
    meeting_id: str
    text: str
    severity: str
    escalated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PrepBriefOut(BaseModel):
    meeting: MeetingOut
    attendees: list[dict]
    previous_summary: str | None
    open_action_items: list[ActionItemOut]
    pending_jira_tickets: list[dict]
    risks: list[RiskOut]
    suggested_questions: list[QuestionOut]
    suggested_agenda: list[str]


class ReportOut(BaseModel):
    id: str
    meeting_id: str
    workspace_id: str
    summary: str | None
    full_json: str | None
    slack_draft: str | None
    email_draft: str | None
    jira_draft: str | None
    slack_sent: bool
    email_sent: bool
    jira_updated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class KnowledgeQueryResponse(BaseModel):
    answer: str
    sources: list[dict]
