from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.core.logging import get_logger
from app.core.security import create_action_token, decode_action_token
from app.models.knowledge import Integration, RetentionPolicy
from app.models.user import AuditLog, User, WorkspaceRole
from app.services.integrations.oauth_providers import (
    build_auth_url,
    exchange_code,
    provider_oauth_config,
    store_tokens,
)

router = APIRouter()

_settings = get_settings()
_logger = get_logger(__name__)

OAUTH_PROVIDERS = ("jira", "google_calendar", "slack", "microsoft_teams")


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
        oauth_available = provider in OAUTH_PROVIDERS and provider_oauth_config(provider) is not None
        if provider in existing:
            integration = existing[provider]
            integrations.append({
                "id": integration.id,
                "provider": integration.provider,
                "status": integration.status,
                "scopes": integration.scopes,
                "oauth_available": oauth_available,
                "mode": "mock" if integration.scopes == "mock" else "oauth",
            })
        else:
            integrations.append({
                "id": None,
                "provider": provider,
                "status": "disconnected",
                "scopes": None,
                "oauth_available": oauth_available,
                "mode": None,
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
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    # Real OAuth flow when client credentials are configured for this provider
    if provider in OAUTH_PROVIDERS and provider_oauth_config(provider):
        # Bind the state to the initiating user (defense-in-depth against CSRF / login-stitching)
        state = create_action_token(f"{workspace_id}:{provider}:{user.id}", "oauth_state", expires_minutes=15)
        auth_url = build_auth_url(provider, state)
        db.add(AuditLog(
            workspace_id=workspace_id,
            user_id=user.id,
            action="integration.oauth_started",
            resource_type="integration",
            detail=provider,
        ))
        await db.flush()
        return {"provider": provider, "status": "redirect", "auth_url": auth_url}

    result = await db.execute(
        select(Integration).where(Integration.workspace_id == workspace_id, Integration.provider == provider)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        integration = Integration(workspace_id=workspace_id, provider=provider)
        db.add(integration)

    # No OAuth credentials configured — connect in mock mode
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
    return {"provider": provider, "status": "connected", "auth_url": None,
            "note": "Using mock integration (no OAuth credentials configured)"}


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


# Mounted at /api/integrations — OAuth providers redirect the browser here, so no user auth;
# the signed `state` token carries the workspace authorization.
oauth_router = APIRouter()


@oauth_router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    def _redirect(workspace_id: str | None, result: str) -> RedirectResponse:
        if workspace_id:
            url = f"{_settings.frontend_url}/workspaces/{workspace_id}/integrations?oauth={result}&provider={provider}"
        else:
            url = f"{_settings.frontend_url}/dashboard?oauth={result}"
        return RedirectResponse(url, status_code=302)

    workspace_id: str | None = None
    initiating_user_id: str | None = None
    try:
        if not state:
            raise ValueError("Missing state")
        subject = decode_action_token(state, "oauth_state")
        parts = subject.split(":")
        if len(parts) < 2:
            raise ValueError("Malformed state")
        workspace_id, state_provider = parts[0], parts[1]
        initiating_user_id = parts[2] if len(parts) > 2 else None
        if state_provider != provider:
            raise ValueError("Provider mismatch in state")
    except ValueError:
        _logger.warning("OAuth callback with invalid state for %s", provider)
        return _redirect(None, "invalid_state")

    if error or not code:
        return _redirect(workspace_id, "denied")

    try:
        tokens = await exchange_code(provider, code)
    except Exception as exc:
        _logger.error("OAuth code exchange failed for %s: %s", provider, exc)
        return _redirect(workspace_id, "error")

    result = await db.execute(
        select(Integration).where(Integration.workspace_id == workspace_id, Integration.provider == provider)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        integration = Integration(workspace_id=workspace_id, provider=provider)
        db.add(integration)

    store_tokens(integration, tokens)
    db.add(AuditLog(
        workspace_id=workspace_id,
        user_id=initiating_user_id,
        action="integration.connected",
        resource_type="integration",
        detail=f"{provider} (oauth)",
    ))
    await db.flush()
    return _redirect(workspace_id, "success")
