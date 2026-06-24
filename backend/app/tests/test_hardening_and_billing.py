from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.security import (
    create_action_token,
    decrypt_secret,
    encrypt_secret,
    validate_password_strength,
)
from app.services import billing as billing_service

_settings = get_settings()


# --- password policy ---

def test_password_policy_rejects_weak_passwords():
    assert validate_password_strength("short") != []
    assert validate_password_strength("alllowercase123") != []   # no uppercase
    assert validate_password_strength("ALLUPPERCASE123") != []   # no lowercase
    assert validate_password_strength("NoDigitsHereYet") != []   # no digit
    assert validate_password_strength("GoodPassw0rd!") == []


@pytest.mark.asyncio
async def test_register_rejects_weak_password(client):
    r = await client.post("/api/auth/register", json={
        "email": "weakpw@ammeet.io",
        "password": "weakpassword",
        "full_name": "Weak PW",
    })
    assert r.status_code == 422
    assert "Password" in str(r.json()["detail"])


# --- token encryption at rest ---

def test_encrypt_decrypt_roundtrip():
    secret = json.dumps({"access_token": "xoxb-secret-token", "refresh_token": "r-123"})
    ciphertext = encrypt_secret(secret)
    assert ciphertext != secret
    assert "xoxb-secret-token" not in ciphertext
    assert decrypt_secret(ciphertext) == secret


def test_decrypt_garbage_raises():
    with pytest.raises(ValueError):
        decrypt_secret("not-a-real-ciphertext")


# --- email verification and password reset flows ---

@pytest.mark.asyncio
async def test_email_verification_flow(client, db_session):
    r = await client.post("/api/auth/register", json={
        "email": "verifyme@ammeet.io",
        "password": "GoodPassw0rd1",
        "full_name": "Verify Me",
    })
    assert r.status_code == 201
    user_id = r.json()["id"]
    assert r.json()["email_verified"] is False

    token = create_action_token(user_id, "email_verify")
    r = await client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200
    assert r.json()["verified"] is True


@pytest.mark.asyncio
async def test_verify_email_rejects_wrong_purpose_token(client, test_user):
    # A password-reset token must not work as an email-verification token
    token = create_action_token(test_user.id, "password_reset")
    r = await client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_password_reset_flow(client, test_user):
    token = create_action_token(test_user.id, "password_reset", expires_minutes=60)
    r = await client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "BrandNewPass1",
    })
    assert r.status_code == 200

    # Old password no longer works, new one does
    r = await client.post("/api/auth/login", json={"email": test_user.email, "password": "test1234"})
    assert r.status_code == 401
    r = await client.post("/api/auth/login", json={"email": test_user.email, "password": "BrandNewPass1"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_does_not_leak_registered_emails(client):
    r = await client.post("/api/auth/forgot-password", json={"email": "nobody@nowhere.io"})
    assert r.status_code == 200
    assert r.json()["sent"] is True


@pytest.mark.asyncio
async def test_password_reset_invalidates_existing_sessions(client, test_user):
    # Obtain a valid access token
    login = await client.post("/api/auth/login", json={"email": test_user.email, "password": "test1234"})
    old_token = login.json()["access_token"]
    assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})).status_code == 200

    # Reset the password -> token_version bumps -> old token must be rejected
    reset_token = create_action_token(test_user.id, "password_reset", expires_minutes=60)
    r = await client.post("/api/auth/reset-password", json={"token": reset_token, "new_password": "RotatedPass123"})
    assert r.status_code == 200

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_reset_token_is_single_use(client, test_user):
    from app.core.redis import get_redis
    try:
        await (await get_redis()).ping()
    except Exception:
        pytest.skip("Redis not available")

    token = create_action_token(test_user.id, "password_reset", expires_minutes=60)
    r1 = await client.post("/api/auth/reset-password", json={"token": token, "new_password": "FirstReset123"})
    assert r1.status_code == 200
    # Replaying the same token must be rejected
    r2 = await client.post("/api/auth/reset-password", json={"token": token, "new_password": "SecondReset123"})
    assert r2.status_code == 400


# --- account lockout (requires Redis) ---

@pytest.mark.asyncio
async def test_account_lockout_after_failed_logins(client, test_user):
    from app.core.redis import get_redis

    try:
        r = await get_redis()
        await r.ping()
    except Exception:
        pytest.skip("Redis not available")

    await r.delete(f"login_failures:{test_user.email}")
    for _ in range(_settings.login_max_attempts):
        resp = await client.post("/api/auth/login", json={
            "email": test_user.email, "password": "definitely-wrong",
        })
        assert resp.status_code == 401

    # Next attempt is locked out even with the right password
    resp = await client.post("/api/auth/login", json={
        "email": test_user.email, "password": "test1234",
    })
    assert resp.status_code == 423
    await r.delete(f"login_failures:{test_user.email}")


# --- billing: plan limits ---

@pytest.mark.asyncio
async def test_free_plan_limit_enforced(db_session, test_workspace):
    limit = billing_service.PLAN_LIMITS["free"]["proxy_sessions"]
    for _ in range(limit):
        await billing_service.check_and_increment_usage(db_session, test_workspace, "proxy_sessions")

    with pytest.raises(HTTPException) as exc:
        await billing_service.check_and_increment_usage(db_session, test_workspace, "proxy_sessions")
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_team_plan_is_unlimited(db_session, test_workspace):
    test_workspace.plan = "team"
    test_workspace.subscription_status = "active"
    for _ in range(10):
        await billing_service.check_and_increment_usage(db_session, test_workspace, "report_generations")
    usage = await billing_service.get_usage(db_session, test_workspace.id)
    assert usage["report_generations"] == 10


@pytest.mark.asyncio
async def test_billing_endpoint_shape(client, auth_token, test_workspace):
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/billing",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["plan"] == "free"
    assert data["billing_enabled"] is False
    assert "proxy_sessions" in data["usage"]
    assert {p["id"] for p in data["plans"]} == {"free", "pro", "team"}


@pytest.mark.asyncio
async def test_mock_checkout_changes_plan(client, auth_token, test_workspace):
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/billing/checkout",
        json={"plan": "pro"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    assert r.json()["mock"] is True

    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/billing",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.json()["plan"] == "pro"


# --- billing: webhook signature verification ---

def test_webhook_signature_verification():
    _settings.stripe_webhook_secret = "whsec_testsecret"
    try:
        payload = json.dumps({"type": "customer.subscription.updated", "data": {"object": {}}}).encode()
        ts = str(int(time.time()))
        sig = hmac.new(b"whsec_testsecret", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()

        event = billing_service.verify_webhook_signature(payload, f"t={ts},v1={sig}")
        assert event["type"] == "customer.subscription.updated"

        with pytest.raises(HTTPException):
            billing_service.verify_webhook_signature(payload, f"t={ts},v1={'0' * 64}")
    finally:
        _settings.stripe_webhook_secret = ""


def test_webhook_accepts_any_of_multiple_v1_signatures():
    _settings.stripe_webhook_secret = "whsec_rotation"
    try:
        payload = json.dumps({"type": "customer.subscription.created", "data": {"object": {}}}).encode()
        ts = str(int(time.time()))
        good = hmac.new(b"whsec_rotation", f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
        # Header carries an old signature first, then the valid one (rotation case)
        header = f"t={ts},v1={'0' * 64},v1={good}"
        event = billing_service.verify_webhook_signature(payload, header)
        assert event["type"] == "customer.subscription.created"
    finally:
        _settings.stripe_webhook_secret = ""


def test_webhook_non_numeric_timestamp_is_400_not_500():
    _settings.stripe_webhook_secret = "whsec_x"
    try:
        with pytest.raises(HTTPException) as exc:
            billing_service.verify_webhook_signature(b"{}", f"t=notanumber,v1={'0' * 64}")
        assert exc.value.status_code == 400
    finally:
        _settings.stripe_webhook_secret = ""


# --- provider crash-safety on malformed upstream payloads ---

@pytest.mark.asyncio
async def test_calendar_empty_entrypoints_does_not_crash():
    import httpx
    from app.services.integrations.oauth_providers import GoogleCalendarProvider

    event = {
        "id": "e1", "summary": "Sync", "start": {"dateTime": "2026-06-21T10:00:00Z"},
        "end": {"dateTime": "2026-06-21T11:00:00Z"},
        # conferenceData present but entryPoints is an empty list (pending conference)
        "conferenceData": {"entryPoints": []},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [event]})

    provider = GoogleCalendarProvider("fake-token")
    transport = httpx.MockTransport(handler)
    import app.services.integrations.oauth_providers as mod
    real_client = httpx.AsyncClient
    mod.httpx.AsyncClient = lambda *a, **k: real_client(transport=transport)
    try:
        events = await provider.get_upcoming_events("ws")
    finally:
        mod.httpx.AsyncClient = real_client
    assert events[0]["meet_link"] is None  # no crash, gracefully null


def test_jira_normalize_handles_empty_adf_content():
    from app.services.integrations.oauth_providers import JiraProvider

    issue = {
        "key": "PROJ-1",
        "fields": {
            "summary": "Test",
            "status": {"name": "To Do"},
            "comment": {"comments": [
                {"body": {"type": "doc", "version": 1, "content": []}},               # empty top-level
                {"body": {"type": "doc", "content": [{"type": "paragraph", "content": []}]}},  # empty inner
            ]},
        },
    }
    # Must not raise IndexError
    result = JiraProvider._normalize(issue)
    assert result["key"] == "PROJ-1"
    assert result["comments"] == []


# --- integrations: mock connect + encrypted storage ---

@pytest.mark.asyncio
async def test_integration_mock_connect(client, auth_token, test_workspace):
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/integrations/slack/connect",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    # No OAuth credentials configured in tests -> mock connection
    assert data["status"] == "connected"
    assert data["auth_url"] is None

    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/integrations",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    slack = next(i for i in r.json() if i["provider"] == "slack")
    assert slack["status"] == "connected"
    assert slack["mode"] == "mock"
    assert slack["oauth_available"] is False


@pytest.mark.asyncio
async def test_oauth_callback_rejects_invalid_state(client):
    r = await client.get(
        "/api/integrations/oauth/slack/callback?code=abc&state=forged-state",
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "oauth=invalid_state" in r.headers["location"]


# --- rate limiting (requires Redis) ---

@pytest.mark.asyncio
async def test_rate_limit_returns_429(client):
    from app.core.redis import get_redis

    try:
        r = await get_redis()
        await r.ping()
    except Exception:
        pytest.skip("Redis not available")

    original = _settings.rate_limit_auth_per_minute
    _settings.rate_limit_auth_per_minute = 2
    try:
        # Clear any counter left over from other tests
        keys = [k async for k in r.scan_iter("ratelimit:forgot_password:*")]
        if keys:
            await r.delete(*keys)

        statuses = []
        for _ in range(4):
            resp = await client.post("/api/auth/forgot-password", json={"email": "ratelimit@test.io"})
            statuses.append(resp.status_code)
        assert 429 in statuses
    finally:
        _settings.rate_limit_auth_per_minute = original
        keys = [k async for k in r.scan_iter("ratelimit:forgot_password:*")]
        if keys:
            await r.delete(*keys)
