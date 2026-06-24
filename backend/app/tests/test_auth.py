from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_register_and_login(client):
    # Register
    r = await client.post("/api/auth/register", json={
        "email": "newuser@ammeet.io",
        "password": "Secure1234xy",
        "full_name": "New User",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "newuser@ammeet.io"
    assert not data["totp_enabled"]

    # Login
    r = await client.post("/api/auth/login", json={
        "email": "newuser@ammeet.io",
        "password": "Secure1234xy",
    })
    assert r.status_code == 200
    tokens = r.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_login_wrong_password(client, test_user):
    r = await client.post("/api/auth/login", json={
        "email": "test@ammeet.io",
        "password": "wrongpassword",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client, auth_token):
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "test@ammeet.io"


@pytest.mark.asyncio
async def test_refresh_token(client, auth_token):
    # Get refresh token
    r = await client.post("/api/auth/login", json={"email": "test@ammeet.io", "password": "test1234"})
    refresh_token = r.json()["refresh_token"]

    r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_mfa_setup_and_verify(client, auth_token):
    # Setup MFA
    r = await client.post("/api/auth/mfa/setup", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "secret" in data
    assert "uri" in data

    # Verify with valid TOTP code
    import pyotp
    totp = pyotp.TOTP(data["secret"])
    r = await client.post(
        "/api/auth/mfa/verify",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"code": totp.now()},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True
