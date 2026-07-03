from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.user import AuditLog, User, Workspace, WorkspaceMember, WorkspaceRole
from app.models.knowledge import RetentionPolicy
from app.schemas.workspace import (
    InviteMemberRequest,
    WorkspaceCreate,
    WorkspaceMemberOut,
    WorkspaceOut,
)

router = APIRouter()


def _make_slug(name: str, suffix: str = "") -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return f"{base}-{suffix}" if suffix else base


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    base_slug = _make_slug(body.name)
    slug = base_slug
    counter = 1
    while True:
        existing = await db.execute(select(Workspace).where(Workspace.slug == slug))
        if not existing.scalar_one_or_none():
            break
        slug = _make_slug(body.name, str(counter))
        counter += 1

    ws = Workspace(name=body.name, description=body.description, slug=slug)
    db.add(ws)
    await db.flush()

    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.OWNER)
    db.add(member)

    # Create default retention policy
    db.add(RetentionPolicy(workspace_id=ws.id))

    db.add(AuditLog(
        workspace_id=ws.id,
        user_id=user.id,
        action="workspace.created",
        resource_type="workspace",
        resource_id=ws.id,
        detail=ws.name,
    ))
    return ws


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Workspace]:
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspace:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberOut)
async def invite_member(
    workspace_id: str,
    body: InviteMemberRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceMember:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.ADMIN)

    result = await db.execute(select(User).where(User.email == body.email))
    invitee = result.scalar_one_or_none()
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found — they must register first")

    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == invitee.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User is already a workspace member")

    member = WorkspaceMember(workspace_id=workspace_id, user_id=invitee.id, role=body.role)
    db.add(member)
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="workspace.member.invited",
        detail=f"{invitee.email} as {body.role}",
    ))
    await db.flush()  # populate member.id / created_at before response serialization
    return member


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberOut])
async def list_members(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkspaceMember]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
    )
    return list(result.scalars().all())
