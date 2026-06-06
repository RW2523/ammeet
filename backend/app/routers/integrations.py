from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.knowledge import Integration, RetentionPolicy
from app.models.user import AuditLog, User, WorkspaceRole

router = APIRouter()


@router.get("/{workspace_id}/integrations")
async def list_integrations(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)

    providers = ["jira", "google_calendar", "slack", "zoom", "microsoft_teams", "notion"]
    result = await db.execute(
        select(Integration).where(Integration.workspace_id == workspace_id)
    )
    existing = {i.provider: i for i in result.scalars().all()}

    integrations = []
    for provider in providers:
        if provider in existing:
            integration = existing[provider]
            integrations.append({
                "id": integration.id,
                "provider": integration.provider,
                "status": integration.status,
                "scopes": integration.scopes,
            })
        else:
            integrations.append({
                "id": None,
                "provider": provider,
                "status": "disconnected",
                "scopes": None,
            })
    return integrations


@router.post("/{workspace_id}/integrations/{provider}/connect")
async def connect_integration(
    workspace_id: str,
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.ADMIN)

    allowed_providers = ["jira", "google_calendar", "slack", "zoom", "microsoft_teams", "notion"]
    if provider not in allowed_providers:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    result = await db.execute(
        select(Integration).where(Integration.workspace_id == workspace_id, Integration.provider == provider)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        integration = Integration(workspace_id=workspace_id, provider=provider)
        db.add(integration)

    # MVP: mark as stub-connected
    integration.status = "connected"
    integration.scopes = "mock"

    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="integration.connected",
        resource_type="integration",
        detail=provider,
    ))
    await db.flush()
    return {"provider": provider, "status": "connected", "note": "Using mock integration in MVP"}


@router.delete("/{workspace_id}/integrations/{provider}/disconnect")
async def disconnect_integration(
    workspace_id: str,
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.ADMIN)

    result = await db.execute(
        select(Integration).where(Integration.workspace_id == workspace_id, Integration.provider == provider)
    )
    integration = result.scalar_one_or_none()
    if integration:
        integration.status = "disconnected"
        integration.encrypted_token = None
        db.add(AuditLog(
            workspace_id=workspace_id,
            user_id=user.id,
            action="integration.disconnected",
            detail=provider,
        ))
        await db.flush()

    return {"provider": provider, "status": "disconnected"}


@router.get("/{workspace_id}/retention-policy")
async def get_retention_policy(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(RetentionPolicy).where(RetentionPolicy.workspace_id == workspace_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        return {"workspace_id": workspace_id, "policy": "default"}
    return {
        "workspace_id": workspace_id,
        "audio_retention_days": policy.audio_retention_days,
        "transcript_retention_days": policy.transcript_retention_days,
        "summary_retention_days": policy.summary_retention_days,
        "action_item_retention_days": policy.action_item_retention_days,
        "sensitive_do_not_store": policy.sensitive_do_not_store,
    }


@router.patch("/{workspace_id}/retention-policy")
async def update_retention_policy(
    workspace_id: str,
    audio_retention_days: int | None = None,
    transcript_retention_days: int | None = None,
    summary_retention_days: int | None = None,
    sensitive_do_not_store: bool | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.ADMIN)
    result = await db.execute(
        select(RetentionPolicy).where(RetentionPolicy.workspace_id == workspace_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        policy = RetentionPolicy(workspace_id=workspace_id)
        db.add(policy)

    if audio_retention_days is not None:
        policy.audio_retention_days = audio_retention_days
    if transcript_retention_days is not None:
        policy.transcript_retention_days = transcript_retention_days
    if summary_retention_days is not None:
        policy.summary_retention_days = summary_retention_days
    if sensitive_do_not_store is not None:
        policy.sensitive_do_not_store = sensitive_do_not_store

    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=user.id,
        action="retention_policy.updated",
    ))
    await db.flush()
    return {"updated": True}
