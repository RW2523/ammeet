from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.user import SubscriptionPlan, UsageRecord, Workspace

_settings = get_settings()
_logger = get_logger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"

# Per-month limits per plan. None = unlimited.
PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    SubscriptionPlan.FREE: {
        "proxy_sessions": 3,
        "ai_question_batches": 10,
        "report_generations": 10,
        "speak_sessions": 5,
    },
    SubscriptionPlan.PRO: {
        "proxy_sessions": 50,
        "ai_question_batches": 200,
        "report_generations": 200,
        "speak_sessions": 200,
    },
    SubscriptionPlan.TEAM: {
        "proxy_sessions": None,
        "ai_question_batches": None,
        "report_generations": None,
        "speak_sessions": None,
    },
}

PLAN_PRICES_USD = {SubscriptionPlan.FREE: 0, SubscriptionPlan.PRO: 29, SubscriptionPlan.TEAM: 99}


def billing_enabled() -> bool:
    return bool(_settings.stripe_secret_key)


def current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def effective_plan(workspace: Workspace) -> str:
    """A workspace's paid plan only counts while the subscription is active or in grace."""
    if workspace.plan != SubscriptionPlan.FREE and workspace.subscription_status in ("active", "trialing", "past_due"):
        return workspace.plan
    if not billing_enabled():
        # No Stripe configured (dev/demo) — honor whatever plan is set on the workspace
        return workspace.plan
    return SubscriptionPlan.FREE


async def get_usage(db: AsyncSession, workspace_id: str) -> dict[str, int]:
    result = await db.execute(
        select(UsageRecord).where(
            UsageRecord.workspace_id == workspace_id,
            UsageRecord.period == current_period(),
        )
    )
    return {rec.metric: rec.count for rec in result.scalars().all()}


async def check_and_increment_usage(db: AsyncSession, workspace: Workspace, metric: str) -> None:
    """Raise 402 if the workspace is over its plan limit for this metric, else count the use."""
    plan = effective_plan(workspace)
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS[SubscriptionPlan.FREE]).get(metric)
    period = current_period()

    result = await db.execute(
        select(UsageRecord.count).where(
            UsageRecord.workspace_id == workspace.id,
            UsageRecord.metric == metric,
            UsageRecord.period == period,
        )
    )
    used = result.scalar_one_or_none() or 0

    if limit is not None and used >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Monthly limit reached for {metric.replace('_', ' ')} on the {plan} plan "
                f"({used}/{limit}). Upgrade your plan to continue."
            ),
        )

    # Atomic upsert so concurrent requests can't lose an increment or collide on
    # the unique (workspace_id, metric, period) constraint (would otherwise 500).
    stmt = pg_insert(UsageRecord).values(
        id=str(uuid.uuid4()),
        workspace_id=workspace.id,
        metric=metric,
        period=period,
        count=1,
    ).on_conflict_do_update(
        index_elements=["workspace_id", "metric", "period"],
        set_={"count": UsageRecord.__table__.c.count + 1},
    )
    await db.execute(stmt)
    await db.flush()


# --- Stripe API (direct httpx, form-encoded like the Stripe API expects) ---

async def _stripe_post(path: str, data: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{STRIPE_API_BASE}{path}",
            data=data,
            auth=(_settings.stripe_secret_key, ""),
        )
        if resp.status_code >= 400:
            _logger.error("Stripe error %s: %s", resp.status_code, resp.text[:500])
            raise HTTPException(status_code=502, detail="Billing provider error")
        return resp.json()


def _price_for_plan(plan: str) -> str:
    price = {
        SubscriptionPlan.PRO: _settings.stripe_price_pro_monthly,
        SubscriptionPlan.TEAM: _settings.stripe_price_team_monthly,
    }.get(plan, "")
    if not price:
        raise HTTPException(status_code=400, detail=f"No Stripe price configured for plan '{plan}'")
    return price


async def ensure_stripe_customer(db: AsyncSession, workspace: Workspace, email: str) -> str:
    if workspace.stripe_customer_id:
        return workspace.stripe_customer_id
    customer = await _stripe_post(
        "/customers",
        {"email": email, "name": workspace.name, "metadata[workspace_id]": workspace.id},
    )
    workspace.stripe_customer_id = customer["id"]
    await db.flush()
    return customer["id"]


async def create_checkout_session(db: AsyncSession, workspace: Workspace, email: str, plan: str) -> str:
    """Create a Stripe Checkout session and return its URL."""
    customer_id = await ensure_stripe_customer(db, workspace, email)
    session = await _stripe_post(
        "/checkout/sessions",
        {
            "customer": customer_id,
            "mode": "subscription",
            "line_items[0][price]": _price_for_plan(plan),
            "line_items[0][quantity]": "1",
            "success_url": f"{_settings.frontend_url}/workspaces/{workspace.id}/billing?status=success",
            "cancel_url": f"{_settings.frontend_url}/workspaces/{workspace.id}/billing?status=canceled",
            "metadata[workspace_id]": workspace.id,
            "metadata[plan]": plan,
            "subscription_data[metadata][workspace_id]": workspace.id,
            "subscription_data[metadata][plan]": plan,
        },
    )
    return session["url"]


async def create_portal_session(workspace: Workspace) -> str:
    if not workspace.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account for this workspace yet")
    session = await _stripe_post(
        "/billing_portal/sessions",
        {
            "customer": workspace.stripe_customer_id,
            "return_url": f"{_settings.frontend_url}/workspaces/{workspace.id}/billing",
        },
    )
    return session["url"]


def verify_webhook_signature(payload: bytes, signature_header: str, tolerance_seconds: int = 300) -> dict[str, Any]:
    """Verify a Stripe webhook signature (t=...,v1=... format) and return the parsed event."""
    secret = _settings.stripe_webhook_secret
    if not secret:
        raise HTTPException(status_code=400, detail="Webhook secret not configured")

    # A header may carry multiple v1 signatures during secret rotation; collect all.
    pairs = [item.split("=", 1) for item in signature_header.split(",") if "=" in item]
    timestamp = next((v for k, v in pairs if k == "t"), None)
    v1_sigs = [v for k, v in pairs if k == "v1"]
    if not timestamp or not v1_sigs:
        raise HTTPException(status_code=400, detail="Malformed signature header")

    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed signature header")

    if abs(time.time() - ts) > tolerance_seconds:
        raise HTTPException(status_code=400, detail="Webhook timestamp outside tolerance")

    signed_payload = f"{timestamp}.".encode() + payload
    computed = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(computed, sig) for sig in v1_sigs):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    return json.loads(payload)


async def _already_processed(event_id: str) -> bool:
    """Idempotency guard: returns True if this Stripe event id was already applied.

    Backed by Redis with a TTL well beyond Stripe's retry window. Fails open
    (treats as not-processed) if Redis is unavailable.
    """
    if not event_id:
        return False
    try:
        from app.core.redis import get_redis

        r = await get_redis()
        was_set = await r.set(f"stripe_event:{event_id}", "1", nx=True, ex=60 * 60 * 24 * 3)
        return not bool(was_set)
    except Exception as exc:
        _logger.warning("Webhook idempotency store unavailable: %s", exc)
        return False


async def apply_subscription_event(db: AsyncSession, event: dict[str, Any]) -> None:
    """Sync workspace plan from Stripe subscription lifecycle events."""
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if event_type not in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        return

    # Skip events we've already applied (Stripe retries + at-least-once delivery).
    if await _already_processed(event.get("id", "")):
        _logger.info("Skipping already-processed Stripe event %s", event.get("id"))
        return

    workspace_id = (obj.get("metadata") or {}).get("workspace_id")
    if not workspace_id:
        # Fall back to customer lookup
        customer_id = obj.get("customer")
        result = await db.execute(select(Workspace).where(Workspace.stripe_customer_id == customer_id))
        workspace = result.scalar_one_or_none()
    else:
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = result.scalar_one_or_none()

    if not workspace:
        _logger.warning("Webhook for unknown workspace (event %s)", event.get("id"))
        return

    new_period_end = None
    period_end = obj.get("current_period_end")
    if period_end:
        new_period_end = datetime.fromtimestamp(period_end, tz=UTC)

    # Out-of-order protection: Stripe does not guarantee delivery order. Ignore an
    # update whose period end is older than what we've already stored, so a stale
    # snapshot can't overwrite the current subscription state. (Deletions always apply.)
    if (
        event_type != "customer.subscription.deleted"
        and new_period_end is not None
        and workspace.current_period_end is not None
        and new_period_end < workspace.current_period_end
    ):
        _logger.info("Ignoring stale subscription event %s for workspace %s", event.get("id"), workspace.id)
        return

    if event_type == "customer.subscription.deleted":
        workspace.plan = SubscriptionPlan.FREE
        workspace.stripe_subscription_id = None
        workspace.subscription_status = "canceled"
        workspace.current_period_end = None
    else:
        plan = (obj.get("metadata") or {}).get("plan") or workspace.plan
        # Only honor plans we recognize; otherwise keep the existing plan.
        if plan not in (SubscriptionPlan.FREE, SubscriptionPlan.PRO, SubscriptionPlan.TEAM):
            plan = workspace.plan
        workspace.plan = plan
        workspace.stripe_subscription_id = obj.get("id")
        workspace.subscription_status = obj.get("status")
        if new_period_end is not None:
            workspace.current_period_end = new_period_end

    await db.flush()
    _logger.info("Workspace %s plan synced to %s (%s)", workspace.id, workspace.plan, workspace.subscription_status)
