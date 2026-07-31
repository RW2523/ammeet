"""Delegate — send an AI body to attend a meeting when the owner is absent.

  POST /api/workspaces/{wid}/meetings/{mid}/delegate/start  — deploy (stage silent|briefed)
  POST /api/workspaces/{wid}/meetings/{mid}/delegate/stop   — graceful leave + wrap
  GET  /api/workspaces/{wid}/meetings/{mid}/delegate/status — session row + live bot status
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.delegate import ApprovalRequest, ApprovalStatus, DelegateSession, DelegateStage
from app.models.meeting import Meeting
from app.models.meeting_bot import BotStatus, MeetingBot
from app.models.user import AuditLog, User, WorkspaceRole
from app.services.delegate_engine import get_active_delegate, launch_delegate
from app.services.live_proxy import get_active_session
from app.services.meeting_assistant import get_active_assistant
from app.services.meeting_bot import get_bot_provider

router = APIRouter()
_settings = get_settings()

_VALID_STAGES = {DelegateStage.SILENT.value, DelegateStage.BRIEFED.value, DelegateStage.INTERACTIVE.value}
# Stages that speak beyond the disclosure and therefore require real TTS up front.
_SPEAKING_STAGES = {DelegateStage.BRIEFED.value, DelegateStage.INTERACTIVE.value}


class DelegateStartRequest(BaseModel):
    stage: str = DelegateStage.SILENT.value  # "silent" | "briefed"


def _session_out(s: DelegateSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "meeting_id": s.meeting_id,
        "workspace_id": s.workspace_id,
        "stage": s.stage,
        "status": s.status,
        "bot_id": s.bot_id,
        "consent_recorded_at": s.consent_recorded_at.isoformat() if s.consent_recorded_at else None,
        "disclosure_logged_at": s.disclosure_logged_at.isoformat() if s.disclosure_logged_at else None,
        "script": json.loads(s.script_json) if s.script_json else None,
        "follow_ups": json.loads(s.follow_ups_json) if s.follow_ups_json else [],
        "error_detail": s.error_detail,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
    }


async def _meeting_or_404(db: AsyncSession, workspace_id: str, meeting_id: str) -> Meeting:
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


@router.post("/{workspace_id}/meetings/{meeting_id}/delegate/start")
async def start_delegate(
    workspace_id: str,
    meeting_id: str,
    body: DelegateStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Deploy the delegate to attend on the owner's behalf. Live events stream on
    the meeting WebSocket /api/ws/meetings/{meeting_id}."""
    meeting = await _meeting_or_404(db, workspace_id, meeting_id)
    # Authorize BEFORE leaking consent state to non-members.
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)

    if body.stage not in _VALID_STAGES:
        raise HTTPException(status_code=422, detail="stage must be 'silent', 'briefed', or 'interactive'")
    # Stage C ships dark: enabling it is an explicit human/legal decision, not a default.
    if body.stage == DelegateStage.INTERACTIVE.value and not _settings.delegate_interactive_enabled:
        raise HTTPException(status_code=403, detail="interactive delegate is disabled pending legal review")
    if not meeting.proxy_consent_given:
        raise HTTPException(
            status_code=403,
            detail="Delegate consent must be given for this meeting before the delegate can attend.",
        )
    # Speaking stages must deliver script/answers out loud — refuse BEFORE joining.
    if body.stage in _SPEAKING_STAGES and _settings.tts_provider == "none":
        raise HTTPException(status_code=422, detail=f"{body.stage} delegate requires TTS (TTS_PROVIDER is 'none')")

    if get_active_delegate(meeting_id) or get_active_session(meeting_id) or get_active_assistant(meeting_id):
        raise HTTPException(status_code=409, detail="A delegate or bot session is already active for this meeting")
    existing_bot = await db.execute(
        select(MeetingBot).where(
            MeetingBot.meeting_id == meeting_id,
            MeetingBot.status.in_([BotStatus.CREATED, BotStatus.JOINING, BotStatus.IN_MEETING]),
        )
    )
    if existing_bot.scalars().first():
        raise HTTPException(status_code=409, detail="A delegate or bot session is already active for this meeting")

    # Nothing to attend: no live bot configured AND no meeting link to hand a bot.
    if _settings.bot_provider == "mock" and not meeting.meeting_url:
        raise HTTPException(
            status_code=503,
            detail="Live bot is not configured and the meeting has no URL. Set a meeting_url or configure BOT_PROVIDER.",
        )

    session = DelegateSession(
        meeting_id=meeting_id,
        workspace_id=workspace_id,
        stage=body.stage,
        created_by_id=current_user.id,
        consent_recorded_at=datetime.now(UTC),  # consent flag verified above
    )
    db.add(session)
    await db.commit()

    await launch_delegate(
        session_id=session.id,
        meeting_id=meeting_id,
        workspace_id=workspace_id,
        owner_name=current_user.full_name or current_user.email,
    )
    return {
        "status": "started",
        "session": _session_out(session),
        "websocket": f"/api/ws/meetings/{meeting_id}",
        "message": "Delegate session started. Connect to the meeting WebSocket for live events.",
    }


@router.post("/{workspace_id}/meetings/{meeting_id}/delegate/stop")
async def stop_delegate(
    workspace_id: str,
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Tell the delegate to leave gracefully and wrap (report + follow-ups)."""
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)
    await _meeting_or_404(db, workspace_id, meeting_id)
    agent = get_active_delegate(meeting_id)
    if not agent:
        return {"status": "not_running", "meeting_id": meeting_id}
    agent.stop()
    return {"status": "stopping", "meeting_id": meeting_id}


@router.get("/{workspace_id}/meetings/{meeting_id}/delegate/status")
async def delegate_status(
    workspace_id: str,
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.VIEWER)
    await _meeting_or_404(db, workspace_id, meeting_id)
    result = await db.execute(
        select(DelegateSession)
        .where(DelegateSession.meeting_id == meeting_id)
        .order_by(DelegateSession.created_at.desc())
    )
    session = result.scalars().first()
    if not session:
        return {"status": "no_delegate", "meeting_id": meeting_id}

    out = _session_out(session)
    out["active"] = get_active_delegate(meeting_id) is not None
    if session.bot_id:
        try:
            info = await get_bot_provider().get_bot_status(session.bot_id)
            out["bot_status"] = info.status
        except Exception as exc:  # noqa: BLE001
            out["bot_status_error"] = str(exc)
    return out


# ── Approvals (interactive delegate, stage C) ──────────────────────────────

_APPROVAL_STATUSES = {s.value for s in ApprovalStatus}


class DecisionRequest(BaseModel):
    decision: str  # "approved" | "declined"


def _approval_out(a: ApprovalRequest, meeting_title: str | None = None) -> dict[str, Any]:
    return {
        "id": a.id,
        "delegate_session_id": a.delegate_session_id,
        "meeting_id": a.meeting_id,
        "meeting_title": meeting_title,
        "workspace_id": a.workspace_id,
        "question_text": a.question_text,
        "proposed_answer": a.proposed_answer,
        "sources": json.loads(a.sources_json) if a.sources_json else [],
        "status": a.status,
        "channel": a.channel,
        "decided_by_id": a.decided_by_id,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
    }


@router.get("/{workspace_id}/approvals")
async def list_approvals(
    workspace_id: str,
    status: str = ApprovalStatus.PENDING.value,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Approval inbox for the workspace — what the delegates are waiting on."""
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)
    if status not in _APPROVAL_STATUSES | {"all"}:
        raise HTTPException(status_code=422, detail="status must be pending|approved|declined|timeout|all")
    query = (
        select(ApprovalRequest, Meeting.title)
        .join(Meeting, ApprovalRequest.meeting_id == Meeting.id)
        .where(ApprovalRequest.workspace_id == workspace_id)
        .order_by(ApprovalRequest.created_at.desc())
    )
    if status != "all":
        query = query.where(ApprovalRequest.status == status)
    rows = (await db.execute(query)).all()
    return [_approval_out(a, title) for a, title in rows]


@router.post("/{workspace_id}/approvals/{approval_id}/decision")
async def decide_approval(
    workspace_id: str,
    approval_id: str,
    body: DecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Approve or decline a proposed answer. The waiting delegate polls the
    committed row, so the decision is COMMITTED here (cross-worker safe)."""
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)
    if body.decision not in (ApprovalStatus.APPROVED.value, ApprovalStatus.DECLINED.value):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'declined'")
    request = (await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id, ApprovalRequest.workspace_id == workspace_id
        )
    )).scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    # Optimistic flip: only a pending request can be decided (races with the
    # delegate's timeout write and with concurrent deciders).
    result = await db.execute(
        update(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id, ApprovalRequest.status == ApprovalStatus.PENDING.value)
        .values(
            status=body.decision,
            decided_by_id=current_user.id,
            decided_at=datetime.now(UTC),
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=409, detail="Approval request was already decided or timed out")
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=current_user.id,
        action="delegate.approval_decided",
        resource_type="approval_request",
        resource_id=approval_id,
        detail=body.decision,
    ))
    await db.commit()
    request = (await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id)
        .execution_options(populate_existing=True)
    )).scalar_one()
    return _approval_out(request)
