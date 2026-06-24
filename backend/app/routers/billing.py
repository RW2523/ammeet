from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.user import AuditLog, SubscriptionPlan, User, Workspace, WorkspaceRole
from app.services import billing

router = APIRouter()


class CheckoutRequest(BaseModel):
    plan: str  # "pro" | "team"


async def _get_workspace(db: AsyncSession, workspace_id: str) -> Workspace:
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.get("/{workspace_id}/billing")
async def get_billing(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    workspace = await _get_workspace(db, workspace_id)
    plan = billing.effective_plan(workspace)
    usage = await billing.get_usage(db, workspace_id)
    limits = billing.PLAN_LIMITS.get(plan, billing.PLAN_LIMITS[SubscriptionPlan.FREE])
    return {
        "plan": plan,
        "subscription_status": workspace.subscription_status,
        "current_period_end": workspace.current_period_end,
        "billing_enabled": billing.billing_enabled(),
        "usage": {
            metric: {"used": usage.get(metric, 0), "limit": limit}
            for metric, limit in limits.items()
        },
        "plans": [
            {
                "id": plan_id,
                "price_usd_monthly": billing.PLAN_PRICES_USD[plan_id],
                "limits": plan_limits,
            }
            for plan_id, plan_limits in billing.PLAN_LIMITS.items()
        ],
    }


@router.post("/{workspace_id}/billing/checkout")
async def create_checkout(
    workspace_id: str,
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.ADMIN)
    if body.plan not in (SubscriptionPlan.PRO, SubscriptionPlan.TEAM):
        raise HTTPException(status_code=400, detail="Plan must be 'pro' or 'team'")
    workspace = await _get_workspace(db, workspace_id)

    if not billing.billing_enabled():
        # Mock mode: apply the plan directly so the full flow is demoable without Stripe
        workspace.plan = body.plan
        workspace.subscription_status = "active"
        db.add(AuditLog(
            workspace_id=workspace_id, user_id=user.id,
            action="billing.plan_changed_mock", detail=body.plan,
        ))
        await db.flush()
        return {"mock": True, "plan": body.plan, "checkout_url": None}

    url = await billing.create_checkout_session(db, workspace, user.email, body.plan)
    db.add(AuditLog(
        workspace_id=workspace_id, user_id=user.id,
        action="billing.checkout_started", detail=body.plan,
    ))
    await db.flush()
    return {"mock": False, "checkout_url": url}


@router.post("/{workspace_id}/billing/portal")
async def create_portal(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.ADMIN)
    workspace = await _get_workspace(db, workspace_id)
    if not billing.billing_enabled():
        raise HTTPException(status_code=400, detail="Billing is not configured on this server")
    url = await billing.create_portal_session(workspace)
    return {"portal_url": url}


# Mounted separately at /api/billing — Stripe calls this, no user auth, signature-verified.
webhook_router = APIRouter()


@webhook_router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    event = billing.verify_webhook_signature(payload, signature)
    await billing.apply_subscription_event(db, event)
    return {"received": True}
