from __future__ import annotations

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import decode_token
from app.models.user import User, WorkspaceMember, WorkspaceRole

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_bearer = HTTPBearer()
_logger = get_logger(__name__)


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(creds.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


async def require_workspace_role(
    workspace_id: str,
    user: User,
    db: AsyncSession,
    min_role: WorkspaceRole = WorkspaceRole.MEMBER,
) -> WorkspaceMember:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a workspace member")

    role_order = [
        WorkspaceRole.VIEWER,
        WorkspaceRole.GUEST,
        WorkspaceRole.MEMBER,
        WorkspaceRole.MANAGER,
        WorkspaceRole.ADMIN,
        WorkspaceRole.OWNER,
    ]
    if role_order.index(member.role) < role_order.index(min_role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient workspace role")

    return member
