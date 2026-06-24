from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.user import User


@pytest.mark.asyncio
async def test_google_login_redirects_to_error_when_not_configured(client):
    # No creds AND no dev-mock (e.g. production) -> redirect back with a clear error.
    with patch("app.services.auth_google.dev_mock_enabled", return_value=False):
        r = await client.get("/api/auth/google/login")
    assert r.status_code in (302, 307)
    assert "error=google_not_configured" in r.headers["location"]


@pytest.mark.asyncio
async def test_google_dev_mock_signs_in_without_credentials(client, db_session):
    # No real Google creds + development env -> the button signs you in as a demo user.
    r = await client.get("/api/auth/google/login")
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert "code=__ammeet_dev_mock__" in loc

    cb = await client.get(loc)  # AsyncClient resolves the relative path; carries the cookie
    assert cb.status_code in (302, 307)
    assert "/auth/callback#access_token=" in cb.headers["location"]

    user = (
        await db_session.execute(select(User).where(User.email == "demo.google@ammeet.dev"))
    ).scalar_one()
    assert user.google_id == "dev-mock-google-sub"
    assert user.auth_provider == "google"


@pytest.mark.asyncio
async def test_google_login_redirects_to_google_when_configured(client):
    with patch("app.services.auth_google.configured", return_value=True):
        r = await client.get("/api/auth/google/login")
    assert r.status_code in (302, 307)
    assert "accounts.google.com" in r.headers["location"]
    # CSRF state cookie must be set.
    assert "g_oauth_state" in r.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_google_callback_creates_and_logs_in_user(client, db_session):
    profile = {
        "sub": "google-sub-12345",
        "email": "alice@gmail.com",
        "name": "Alice Example",
        "email_verified": True,
        "picture": None,
    }
    with patch("app.services.auth_google.configured", return_value=True):
        # 1) start the flow to obtain a valid state cookie
        start = await client.get("/api/auth/google/login")
        state = client.cookies.get("g_oauth_state")
        assert state

        # 2) Google redirects back; stub the token/userinfo exchange
        with patch("app.services.auth_google.exchange_code", new=AsyncMock(return_value=profile)):
            cb = await client.get(f"/api/auth/google/callback?code=authcode&state={state}")

    assert cb.status_code in (302, 307)
    loc = cb.headers["location"]
    assert "/auth/callback#access_token=" in loc
    assert "refresh_token=" in loc

    user = (await db_session.execute(select(User).where(User.email == "alice@gmail.com"))).scalar_one()
    assert user.google_id == "google-sub-12345"
    assert user.auth_provider == "google"
    assert user.hashed_password is None
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_google_callback_links_existing_email_account(client, db_session):
    existing = User(
        email="bob@gmail.com",
        full_name="Bob",
        hashed_password=hash_password("Password123"),
        email_verified=False,
    )
    db_session.add(existing)
    await db_session.flush()

    profile = {"sub": "sub-bob-999", "email": "bob@gmail.com", "name": "Bob", "email_verified": True, "picture": None}
    with patch("app.services.auth_google.configured", return_value=True):
        await client.get("/api/auth/google/login")
        state = client.cookies.get("g_oauth_state")
        with patch("app.services.auth_google.exchange_code", new=AsyncMock(return_value=profile)):
            cb = await client.get(f"/api/auth/google/callback?code=c&state={state}")

    assert cb.status_code in (302, 307)
    await db_session.refresh(existing)
    assert existing.google_id == "sub-bob-999"  # linked, not duplicated
    assert existing.email_verified is True


@pytest.mark.asyncio
async def test_google_callback_refuses_to_link_unverified_email(client, db_session):
    existing = User(
        email="dave@gmail.com",
        full_name="Dave",
        hashed_password=hash_password("Password123"),
        email_verified=True,
    )
    db_session.add(existing)
    await db_session.flush()

    # Google says the email is NOT verified -> must refuse to link (account-takeover guard).
    profile = {"sub": "sub-dave", "email": "dave@gmail.com", "name": "Dave", "email_verified": False, "picture": None}
    with patch("app.services.auth_google.configured", return_value=True):
        await client.get("/api/auth/google/login")
        state = client.cookies.get("g_oauth_state")
        with patch("app.services.auth_google.exchange_code", new=AsyncMock(return_value=profile)):
            cb = await client.get(f"/api/auth/google/callback?code=c&state={state}")

    assert "error=google_unverified" in cb.headers["location"]
    await db_session.refresh(existing)
    assert existing.google_id is None  # not linked


@pytest.mark.asyncio
async def test_google_callback_rejects_bad_state(client):
    with patch("app.services.auth_google.configured", return_value=True):
        await client.get("/api/auth/google/login")
        cb = await client.get("/api/auth/google/callback?code=c&state=forged-state")
    assert cb.status_code in (302, 307)
    assert "error=google_state" in cb.headers["location"]


@pytest.mark.asyncio
async def test_email_casing_is_normalized_across_register_login_and_google(client, db_session):
    # Register with mixed-case email...
    r = await client.post("/api/auth/register", json={
        "email": "Mixed.Case@Example.com", "password": "Secure1234xy", "full_name": "Mixed",
    })
    assert r.status_code == 201
    # ...login with a different casing still works (normalized to lowercase).
    r = await client.post("/api/auth/login", json={"email": "mixed.case@EXAMPLE.com", "password": "Secure1234xy"})
    assert r.status_code == 200

    # ...and Google sign-in links the SAME account (no duplicate), matching by lowercase.
    profile = {"sub": "sub-mixed", "email": "mixed.case@example.com", "name": "Mixed", "email_verified": True, "picture": None}
    with patch("app.services.auth_google.configured", return_value=True):
        await client.get("/api/auth/google/login")
        state = client.cookies.get("g_oauth_state")
        with patch("app.services.auth_google.exchange_code", new=AsyncMock(return_value=profile)):
            await client.get(f"/api/auth/google/callback?code=c&state={state}")
    rows = (await db_session.execute(select(User).where(User.email == "mixed.case@example.com"))).scalars().all()
    assert len(rows) == 1 and rows[0].google_id == "sub-mixed"


@pytest.mark.asyncio
async def test_google_only_user_cannot_password_login(client, db_session):
    user = User(
        email="carol@gmail.com",
        full_name="Carol",
        hashed_password=None,
        google_id="sub-carol",
        auth_provider="google",
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    r = await client.post("/api/auth/login", json={"email": "carol@gmail.com", "password": "anything-at-all"})
    assert r.status_code == 401
