from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.meeting import Meeting, Question, QuestionStatus
from app.models.user import AuditLog, User, WorkspaceRole
from app.schemas.meeting import QuestionCreate, QuestionOut, QuestionUpdate

router = APIRouter()


@router.get("/{workspace_id}/meetings/{meeting_id}/questions", response_model=list[QuestionOut])
async def list_questions(
    workspace_id: str,
    meeting_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Question]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(Question)
        .where(Question.meeting_id == meeting_id, Question.workspace_id == workspace_id)
        .order_by(Question.sort_order, Question.created_at)
    )
    return list(result.scalars().all())


@router.post("/{workspace_id}/meetings/{meeting_id}/questions", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
async def create_question(
    workspace_id: str,
    meeting_id: str,
    body: QuestionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Question:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Meeting not found")

    question = Question(meeting_id=meeting_id, workspace_id=workspace_id, **body.model_dump())
    db.add(question)
    await db.flush()
    return question


@router.patch("/{workspace_id}/meetings/{meeting_id}/questions/{question_id}", response_model=QuestionOut)
async def update_question(
    workspace_id: str,
    meeting_id: str,
    question_id: str,
    body: QuestionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Question:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Question).where(
            Question.id == question_id,
            Question.meeting_id == meeting_id,
            Question.workspace_id == workspace_id,
        )
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    # Log proxy_allowed changes for audit
    if body.proxy_allowed is not None and body.proxy_allowed != question.proxy_allowed:
        db.add(AuditLog(
            workspace_id=workspace_id,
            user_id=user.id,
            action="question.proxy_flag.changed",
            resource_type="question",
            resource_id=question_id,
            detail=f"proxy_allowed={body.proxy_allowed}",
        ))

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(question, field, value)
    await db.flush()
    return question


@router.delete("/{workspace_id}/meetings/{meeting_id}/questions/{question_id}", status_code=204)
async def delete_question(
    workspace_id: str,
    meeting_id: str,
    question_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Question).where(
            Question.id == question_id,
            Question.meeting_id == meeting_id,
            Question.workspace_id == workspace_id,
        )
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    await db.delete(question)
    return Response(status_code=204)


@router.post("/{workspace_id}/meetings/{meeting_id}/questions/bulk-approve")
async def bulk_approve_for_proxy(
    workspace_id: str,
    meeting_id: str,
    question_ids: list[str],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(Question).where(
            Question.id.in_(question_ids),
            Question.meeting_id == meeting_id,
            Question.workspace_id == workspace_id,
        )
    )
    questions = list(result.scalars().all())
    for q in questions:
        if not q.human_only:
            q.proxy_allowed = True

    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="questions.bulk_proxy_approved",
        resource_type="meeting",
        resource_id=meeting_id,
        detail=f"{len(questions)} questions approved for proxy",
    ))
    await db.flush()
    return {"approved": len(questions)}
