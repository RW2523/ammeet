from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.knowledge import KnowledgeChunk
from app.models.meeting import ActionItem, ContextSource, Meeting, Report
from app.models.user import AuditLog, User, Workspace, WorkspaceMember
from app.schemas.auth import UserOut

router = APIRouter()


async def _require_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required")
    return user


@router.get("/users", response_model=list[UserOut])
async def list_users(
    user: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


@router.get("/audit-logs")
async def get_audit_logs(
    workspace_id: str | None = None,
    limit: int = 100,
    user: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if workspace_id:
        query = query.where(AuditLog.workspace_id == workspace_id)
    result = await db.execute(query)
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "workspace_id": log.workspace_id,
            "user_id": log.user_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "detail": log.detail,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.delete("/workspaces/{workspace_id}/data")
async def delete_workspace_data(
    workspace_id: str,
    user: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GDPR/CCPA: Delete all data for a workspace (right to erasure)."""
    # Delete knowledge chunks
    chunks = await db.execute(select(KnowledgeChunk).where(KnowledgeChunk.workspace_id == workspace_id))
    for chunk in chunks.scalars().all():
        await db.delete(chunk)

    # Delete meetings and cascades (context_sources, questions, answers, etc.)
    meetings = await db.execute(select(Meeting).where(Meeting.workspace_id == workspace_id))
    for meeting in meetings.scalars().all():
        await db.delete(meeting)

    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="workspace.data.deleted",
        detail="GDPR/CCPA erasure request",
    ))
    await db.flush()
    return {"deleted": True, "workspace_id": workspace_id}


@router.get("/workspaces/{workspace_id}/export")
async def export_workspace_data(
    workspace_id: str,
    user: User = Depends(_require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """GDPR/CCPA: Export all data for a workspace."""
    meetings_result = await db.execute(select(Meeting).where(Meeting.workspace_id == workspace_id))
    meetings = meetings_result.scalars().all()

    export = {
        "workspace_id": workspace_id,
        "meetings": [
            {
                "id": m.id,
                "title": m.title,
                "purpose": m.purpose,
                "mode": m.mode,
                "status": m.status,
                "created_at": m.created_at.isoformat(),
            }
            for m in meetings
        ],
    }

    # Action items
    action_items_result = await db.execute(
        select(ActionItem).where(ActionItem.workspace_id == workspace_id)
    )
    export["action_items"] = [
        {"id": ai.id, "title": ai.title, "owner": ai.owner, "deadline": ai.deadline}
        for ai in action_items_result.scalars().all()
    ]

    return export
