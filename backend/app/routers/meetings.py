from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.meeting import (
    ActionItem,
    Answer,
    ContextSource,
    Decision,
    Meeting,
    MeetingStatus,
    Person,
    Question,
    QuestionPriority,
    QuestionStatus,
    Risk,
)
from app.models.user import AuditLog, User, Workspace, WorkspaceRole
from app.schemas.meeting import (
    ActionItemOut,
    AnswerCreate,
    AnswerOut,
    DecisionOut,
    MeetingCreate,
    MeetingOut,
    MeetingUpdate,
    PrepBriefOut,
    RiskOut,
)
from app.services.billing import check_and_increment_usage
from app.services.extraction import chunk_text, extract_from_text
from app.services.calendar_sync import sync_workspace_calendar
from app.services.integrations import get_calendar, get_jira
from app.services.knowledge_rag import store_chunks
from app.services.question_generator import generate_questions

router = APIRouter()


async def _get_meeting_or_404(workspace_id: str, meeting_id: str, db: AsyncSession) -> Meeting:
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


@router.post("/{workspace_id}/meetings", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    workspace_id: str,
    body: MeetingCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Meeting:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    meeting = Meeting(workspace_id=workspace_id, **body.model_dump())
    db.add(meeting)
    await db.flush()
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="meeting.created",
        resource_type="meeting",
        resource_id=meeting.id,
        detail=meeting.title,
    ))
    return meeting


@router.get("/{workspace_id}/calendar/events")
async def list_calendar_events(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Upcoming calendar events (with join links) for the connected calendar.

    Returns real Google Calendar events when the workspace has connected Google
    Calendar via OAuth, otherwise mock fixtures. Used to create a meeting (and
    auto-join bot) directly from a calendar event.
    """
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    calendar = await get_calendar(db, workspace_id)
    events = await calendar.get_upcoming_events(workspace_id)
    return events


@router.post("/{workspace_id}/calendar/sync")
async def sync_calendar_auto_join(
    workspace_id: str,
    auto_join: bool = True,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Auto-discover upcoming calendar events with join links and create auto-join
    meetings for them. Triggering this is the user's consent to let the bot attend.
    Idempotent — re-running only adds newly-discovered events."""
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    stats = await sync_workspace_calendar(db, workspace_id, enable_auto_join=auto_join)
    # Record who enabled auto-attend and how many meetings it covered (consent trail).
    db.add(AuditLog(
        user_id=user.id,
        workspace_id=workspace_id,
        action="calendar.auto_join_sync",
        resource_type="workspace",
        resource_id=workspace_id,
        detail=f"auto_join={auto_join} created={stats['created']} scanned={stats['scanned']}",
    ))
    return {"status": "ok", **stats}


@router.get("/{workspace_id}/meetings", response_model=list[MeetingOut])
async def list_meetings(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Meeting]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(Meeting)
        .where(Meeting.workspace_id == workspace_id)
        .order_by(Meeting.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{workspace_id}/meetings/{meeting_id}", response_model=MeetingOut)
async def get_meeting(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Meeting:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    return await _get_meeting_or_404(workspace_id, meeting_id, db)


@router.patch("/{workspace_id}/meetings/{meeting_id}", response_model=MeetingOut)
async def update_meeting(
    workspace_id: str,
    meeting_id: str,
    body: MeetingUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Meeting:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    meeting = await _get_meeting_or_404(workspace_id, meeting_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(meeting, field, value)
    await db.flush()
    return meeting


@router.post("/{workspace_id}/meetings/{meeting_id}/start", response_model=MeetingOut)
async def start_meeting(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Meeting:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    meeting = await _get_meeting_or_404(workspace_id, meeting_id, db)
    if meeting.status == MeetingStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Meeting already in progress")
    meeting.status = MeetingStatus.IN_PROGRESS
    meeting.started_at = datetime.now(UTC)
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="meeting.started",
        resource_type="meeting",
        resource_id=meeting.id,
    ))
    await db.flush()
    return meeting


@router.post("/{workspace_id}/meetings/{meeting_id}/end", response_model=MeetingOut)
async def end_meeting(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Meeting:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    meeting = await _get_meeting_or_404(workspace_id, meeting_id, db)
    meeting.status = MeetingStatus.COMPLETED
    meeting.ended_at = datetime.now(UTC)
    await db.flush()
    return meeting


@router.post("/{workspace_id}/meetings/{meeting_id}/upload-context")
async def upload_context(
    workspace_id: str,
    meeting_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    meeting = await _get_meeting_or_404(workspace_id, meeting_id, db)

    content = await file.read()
    raw_text = content.decode("utf-8", errors="replace")

    source = ContextSource(
        meeting_id=meeting.id,
        workspace_id=workspace_id,
        source_type="upload",
        filename=file.filename,
        raw_text=raw_text[:50000],  # cap at 50k chars
        extraction_status="pending",
    )
    db.add(source)
    await db.flush()

    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="context.uploaded",
        resource_type="context_source",
        resource_id=source.id,
        detail=file.filename,
    ))

    # Pass only the id — the background task opens its OWN session, because the
    # request-scoped `db` is already closed by the time BackgroundTasks runs.
    background_tasks.add_task(_process_context_source, source.id)

    return {"id": source.id, "status": "processing", "filename": file.filename}


async def _process_context_source(source_id: str) -> None:
    """Background task: extract and embed a context source (own DB session)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ContextSource).where(ContextSource.id == source_id))
        source = result.scalar_one_or_none()
        if not source or not source.raw_text:
            return

        source.extraction_status = "processing"
        await db.flush()

        try:
            extracted = await extract_from_text(source.raw_text)
            source.extracted_json = json.dumps(extracted)
            source.extraction_status = "done"

            # Embed into knowledge base
            chunks = await chunk_text(source.raw_text)
            await store_chunks(
                db,
                workspace_id=source.workspace_id,
                chunks=chunks,
                source_type="transcript",
                meeting_id=source.meeting_id,
                source_id=source.id,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            source.extraction_status = "failed"
            await db.commit()


@router.get("/{workspace_id}/meetings/{meeting_id}/prep-brief", response_model=PrepBriefOut)
async def get_prep_brief(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    meeting = await _get_meeting_or_404(workspace_id, meeting_id, db)

    people_result = await db.execute(select(Person).where(Person.workspace_id == workspace_id))
    people = list(people_result.scalars().all())

    jira = await get_jira(db, workspace_id)
    jira_tickets = await jira.get_tickets(workspace_id)

    calendar = await get_calendar(db, workspace_id)
    events = await calendar.get_upcoming_events(workspace_id)
    attendees = []
    for event in events:
        if meeting.calendar_event_id and event.get("id") == meeting.calendar_event_id:
            attendees = event.get("attendees", [])
            break
    if not attendees:
        attendees = [{"name": p.name, "role": p.role, "email": p.email} for p in people]

    # Get previous meeting summary from context sources
    sources_result = await db.execute(
        select(ContextSource)
        .where(ContextSource.meeting_id == meeting.id, ContextSource.extraction_status == "done")
        .order_by(ContextSource.created_at.desc())
        .limit(1)
    )
    source = sources_result.scalar_one_or_none()
    previous_summary = None
    if source and source.extracted_json:
        extracted = json.loads(source.extracted_json)
        previous_summary = extracted.get("summary")

    # Open action items from previous meetings
    action_items_result = await db.execute(
        select(ActionItem)
        .where(ActionItem.workspace_id == workspace_id, ActionItem.status == "open")
        .order_by(ActionItem.created_at.desc())
        .limit(10)
    )
    open_action_items = list(action_items_result.scalars().all())

    # Risks from this meeting
    risks_result = await db.execute(select(Risk).where(Risk.meeting_id == meeting.id))
    risks = list(risks_result.scalars().all())

    # Questions already generated
    questions_result = await db.execute(
        select(Question)
        .where(Question.meeting_id == meeting.id)
        .order_by(Question.sort_order)
    )
    questions = list(questions_result.scalars().all())

    suggested_agenda = [
        "Review previous meeting action items",
        "Status update on open Jira tickets",
        "Address blockers",
        "Confirm decisions and approvals",
        "Set next steps and owners",
    ]
    if meeting.purpose:
        suggested_agenda.insert(0, meeting.purpose)

    return {
        "meeting": meeting,
        "attendees": attendees,
        "previous_summary": previous_summary,
        "open_action_items": open_action_items,
        "pending_jira_tickets": [t for t in jira_tickets if t["status"] in ("In Progress", "Review", "To Do")][:5],
        "risks": risks,
        "suggested_questions": questions[:15],
        "suggested_agenda": suggested_agenda,
    }


@router.post("/{workspace_id}/meetings/{meeting_id}/generate-questions")
async def generate_meeting_questions(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    meeting = await _get_meeting_or_404(workspace_id, meeting_id, db)

    workspace_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = workspace_result.scalar_one()
    await check_and_increment_usage(db, workspace, "ai_question_batches")

    people_result = await db.execute(select(Person).where(Person.workspace_id == workspace_id))
    people = [{"name": p.name, "role": p.role, "current_work": p.current_work, "follow_up": p.follow_up} for p in people_result.scalars().all()]

    jira = await get_jira(db, workspace_id)
    jira_tickets = await jira.get_tickets(workspace_id)

    # Get knowledge chunks
    from app.services.knowledge_rag import similarity_search
    chunks = await similarity_search(db, workspace_id, "meeting context", limit=6)
    knowledge_texts = [c.chunk_text for c in chunks]

    # Get previous summaries from sources
    sources_result = await db.execute(
        select(ContextSource)
        .where(ContextSource.meeting_id == meeting.id, ContextSource.extraction_status == "done")
    )
    sources = list(sources_result.scalars().all())
    previous_summary = None
    open_action_items = []
    for source in sources:
        if source.extracted_json:
            data = json.loads(source.extracted_json)
            if not previous_summary:
                previous_summary = data.get("summary")
            open_action_items.extend([ai["title"] for ai in data.get("action_items", [])])

    context = {
        "meeting_purpose": meeting.purpose,
        "previous_summary": previous_summary,
        "open_action_items": open_action_items[:10],
    }

    raw_questions = await generate_questions(context, knowledge_texts, jira_tickets, people)

    generated = []
    for i, q in enumerate(raw_questions):
        question = Question(
            meeting_id=meeting.id,
            workspace_id=workspace_id,
            text=q.get("text", ""),
            category=q.get("category", "general"),
            priority=q.get("priority", "must_ask"),
            proxy_allowed=q.get("proxy_allowed", False),
            human_only=q.get("human_only", False),
            confidence=q.get("confidence"),
            source_context=q.get("source_context"),
            sort_order=i,
        )
        db.add(question)
        generated.append(question)

    await db.flush()
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="questions.generated",
        resource_type="meeting",
        resource_id=meeting.id,
        detail=f"{len(generated)} questions",
    ))
    return {"generated": len(generated)}


@router.post("/{workspace_id}/meetings/{meeting_id}/answers", response_model=AnswerOut)
async def add_answer(
    workspace_id: str,
    meeting_id: str,
    body: AnswerCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Answer:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    await _get_meeting_or_404(workspace_id, meeting_id, db)

    answer = Answer(
        meeting_id=meeting_id,
        workspace_id=workspace_id,
        **body.model_dump(),
    )
    db.add(answer)

    # Update question status if linked
    if body.question_id:
        q_result = await db.execute(select(Question).where(Question.id == body.question_id))
        q = q_result.scalar_one_or_none()
        if q:
            q.status = QuestionStatus.ANSWERED

    await db.flush()
    return answer


@router.get("/{workspace_id}/meetings/{meeting_id}/answers", response_model=list[AnswerOut])
async def list_answers(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Answer]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(Answer).where(Answer.meeting_id == meeting_id, Answer.workspace_id == workspace_id)
    )
    return list(result.scalars().all())
