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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.delegate import DelegateSession, DelegateStage
from app.models.meeting import Meeting
from app.models.meeting_bot import BotStatus, MeetingBot
from app.models.user import User, WorkspaceRole
from app.services.delegate_engine import get_active_delegate, launch_delegate
from app.services.live_proxy import get_active_session
from app.services.meeting_assistant import get_active_assistant
from app.services.meeting_bot import get_bot_provider

router = APIRouter()
_settings = get_settings()

_VALID_STAGES = {DelegateStage.SILENT.value, DelegateStage.BRIEFED.value}


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
        raise HTTPException(status_code=422, detail="stage must be 'silent' or 'briefed'")
    if not meeting.proxy_consent_given:
        raise HTTPException(
            status_code=403,
            detail="Delegate consent must be given for this meeting before the delegate can attend.",
        )
    # A briefed delegate must deliver the script out loud — refuse BEFORE joining.
    if body.stage == DelegateStage.BRIEFED.value and _settings.tts_provider == "none":
        raise HTTPException(status_code=422, detail="briefed delegate requires TTS (TTS_PROVIDER is 'none')")

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
