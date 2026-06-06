from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.meeting import Meeting, MeetingMode, MeetingStatus, Question, QuestionStatus, Report
from app.models.user import AuditLog, User, WorkspaceRole
from app.schemas.meeting import ReportOut
from app.services.proxy_engine import run_proxy_session
from app.services.report_generator import generate_report, send_slack_draft

router = APIRouter()


@router.get("/{workspace_id}/meetings/{meeting_id}/reports", response_model=list[ReportOut])
async def list_reports(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Report]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(Report)
        .where(Report.meeting_id == meeting_id, Report.workspace_id == workspace_id)
        .order_by(Report.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{workspace_id}/meetings/{meeting_id}/reports/generate", response_model=ReportOut)
async def generate_meeting_report(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Report:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    report = await generate_report(db, meeting)
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="report.generated",
        resource_type="report",
        resource_id=report.id,
    ))
    await db.flush()
    return report


@router.post("/{workspace_id}/meetings/{meeting_id}/proxy/start")
async def start_proxy_session(
    workspace_id: str,
    meeting_id: str,
    simulate: bool = True,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Start a Transparent Proxy session. Streams SSE events.
    
    The proxy:
    1. Logs the mandatory disclosure intro
    2. Asks all proxy_allowed questions
    3. Escalates restricted topics
    4. Asks KB-grounded clarifying questions when answers are incomplete
    5. Never makes commitments or final decisions
    """
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.mode != MeetingMode.PROXY:
        raise HTTPException(status_code=400, detail="Meeting mode must be set to 'proxy' to start a proxy session")

    if not meeting.proxy_consent_given:
        raise HTTPException(
            status_code=400,
            detail="Proxy consent must be given before starting a proxy session. Update the meeting with proxy_consent_given=true.",
        )

    questions_result = await db.execute(
        select(Question)
        .where(Question.meeting_id == meeting_id, Question.status == QuestionStatus.PENDING)
        .order_by(Question.sort_order)
    )
    questions = list(questions_result.scalars().all())

    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="proxy.session.started",
        resource_type="meeting",
        resource_id=meeting_id,
        detail=f"simulate={simulate}, questions={len(questions)}",
    ))
    await db.flush()

    async def event_stream() -> AsyncGenerator[str, None]:
        gen = await run_proxy_session(db, meeting, user.full_name, questions, simulate_answers=simulate)
        async for event in gen:
            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(0)
        # After proxy session, auto-generate report
        try:
            await generate_report(db, meeting)
            meeting.status = MeetingStatus.COMPLETED
            await db.commit()
            yield f"data: {json.dumps({'type': 'report_ready'})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{workspace_id}/meetings/{meeting_id}/reports/{report_id}/send-slack")
async def send_slack_message(
    workspace_id: str,
    meeting_id: str,
    report_id: str,
    channel: str = "general",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Review-gated: sends Slack draft only after explicit user action."""
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.workspace_id == workspace_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="report.slack.sent",
        resource_type="report",
        resource_id=report_id,
        detail=f"channel={channel}",
    ))

    result_data = await send_slack_draft(db, report, channel)
    return result_data
