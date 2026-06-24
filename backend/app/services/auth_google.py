"""Google OIDC "Sign in with Google" for the AmMeeting user account.

This is SEPARATE from the Google *Calendar* integration OAuth (which authorizes a
workspace to read calendar events). This one authenticates a person into AmMeeting:
Google → id/userinfo → find-or-create a User → issue our own JWTs.

Reuses the existing google_client_id / google_client_secret. Empty creds ->
`configured()` returns False and the login endpoint reports that cleanly.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

_settings = get_settings()
_logger = get_logger(__name__)

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE = "openid email profile"


def configured() -> bool:
    return bool(_settings.google_client_id and _settings.google_client_secret)


# ── Dev mock ──────────────────────────────────────────────────────────────────
# When real Google credentials aren't set, local development still gets a working
# "Continue with Google" button: it signs you in as a demo Google account without
# any external round-trip. Disabled outside development and whenever real creds exist.
DEV_MOCK_CODE = "__ammeet_dev_mock__"


def dev_mock_enabled() -> bool:
    return not configured() and _settings.environment == "development"


def mock_profile() -> dict[str, Any]:
    return {
        "sub": "dev-mock-google-sub",
        "email": "demo.google@ammeet.dev",
        "name": "Demo Google User",
        "email_verified": True,
        "picture": None,
    }


def redirect_uri() -> str:
    return f"{_settings.webhook_base_url}/api/auth/google/callback"


def build_login_url(state: str) -> str:
    params = {
        "client_id": _settings.google_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": _SCOPE,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
        "include_granted_scopes": "true",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Exchange the auth code for tokens, then fetch the user's profile.

    Returns {sub, email, name, email_verified, picture}. Raises on failure.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": _settings.google_client_id,
                "client_secret": _settings.google_client_secret,
                "code": code,
                "redirect_uri": redirect_uri(),
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise ValueError("Google did not return an access token")

        # The userinfo endpoint is served over TLS directly by Google in response to
        # the token we just minted, so we can trust it without verifying the id_token
        # signature ourselves.
        info_resp = await client.get(
            _USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        info_resp.raise_for_status()
        info = info_resp.json()

    sub = info.get("sub")
    email = info.get("email")
    if not sub or not email:
        raise ValueError("Google profile missing sub/email")
    return {
        "sub": str(sub),
        "email": email.lower(),
        "name": info.get("name") or email.split("@")[0],
        "email_verified": bool(info.get("email_verified", False)),
        "picture": info.get("picture"),
    }
