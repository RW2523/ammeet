from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_secret, encrypt_secret
from app.models.knowledge import Integration

_settings = get_settings()
_logger = get_logger(__name__)


# --- provider OAuth configuration ---

def provider_oauth_config(provider: str) -> dict[str, Any] | None:
    """Return OAuth endpoints/credentials for a provider, or None if not configured."""
    redirect_uri = f"{_settings.webhook_base_url}/api/integrations/oauth/{provider}/callback"
    configs: dict[str, dict[str, Any]] = {
        "google_calendar": {
            "client_id": _settings.google_client_id,
            "client_secret": _settings.google_client_secret,
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scope": "https://www.googleapis.com/auth/calendar.readonly",
            "extra_auth_params": {"access_type": "offline", "prompt": "consent"},
            "redirect_uri": redirect_uri,
        },
        "slack": {
            "client_id": _settings.slack_client_id,
            "client_secret": _settings.slack_client_secret,
            "auth_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "scope": "chat:write,channels:read,channels:join",
            "extra_auth_params": {},
            "redirect_uri": redirect_uri,
        },
        "jira": {
            "client_id": _settings.jira_client_id,
            "client_secret": _settings.jira_client_secret,
            "auth_url": "https://auth.atlassian.com/authorize",
            "token_url": "https://auth.atlassian.com/oauth/token",
            "scope": "read:jira-work offline_access",
            "extra_auth_params": {"audience": "api.atlassian.com", "prompt": "consent"},
            "redirect_uri": redirect_uri,
        },
        "microsoft_teams": {
            "client_id": _settings.microsoft_client_id,
            "client_secret": _settings.microsoft_client_secret,
            "auth_url": f"https://login.microsoftonline.com/{_settings.microsoft_tenant}/oauth2/v2.0/authorize",
            "token_url": f"https://login.microsoftonline.com/{_settings.microsoft_tenant}/oauth2/v2.0/token",
            # Reading calendar events is enough to get Teams join links (onlineMeeting.joinUrl)
            "scope": "offline_access User.Read Calendars.Read",
            "extra_auth_params": {"response_mode": "query", "prompt": "consent"},
            "redirect_uri": redirect_uri,
        },
    }
    config = configs.get(provider)
    if not config or not config["client_id"] or not config["client_secret"]:
        return None
    return config


def build_auth_url(provider: str, state: str) -> str | None:
    config = provider_oauth_config(provider)
    if not config:
        return None
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
        **config["extra_auth_params"],
    }
    return f"{config['auth_url']}?{urlencode(params)}"


async def exchange_code(provider: str, code: str) -> dict[str, Any]:
    """Exchange an authorization code for tokens. Returns the normalized token payload."""
    config = provider_oauth_config(provider)
    if not config:
        raise ValueError(f"OAuth not configured for {provider}")

    async with httpx.AsyncClient(timeout=30) as client:
        if provider == "jira":
            # Atlassian expects JSON
            resp = await client.post(config["token_url"], json={
                "grant_type": "authorization_code",
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": code,
                "redirect_uri": config["redirect_uri"],
            })
        else:
            resp = await client.post(config["token_url"], data={
                "grant_type": "authorization_code",
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "code": code,
                "redirect_uri": config["redirect_uri"],
            })
        resp.raise_for_status()
        data = resp.json()

    if provider == "slack" and not data.get("ok", True):
        raise ValueError(f"Slack OAuth error: {data.get('error')}")

    token_payload: dict[str, Any] = {
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "expires_at": (
            (datetime.now(UTC) + timedelta(seconds=int(data["expires_in"]))).isoformat()
            if data.get("expires_in") else None
        ),
        "scope": data.get("scope"),
    }

    if provider == "slack":
        token_payload["team"] = (data.get("team") or {}).get("name")
        token_payload["bot_user_id"] = data.get("bot_user_id")

    if provider == "jira":
        # Resolve the Jira Cloud site this token can access
        async with httpx.AsyncClient(timeout=30) as client:
            resources = await client.get(
                "https://api.atlassian.com/oauth/token/accessible-resources",
                headers={"Authorization": f"Bearer {token_payload['access_token']}"},
            )
            resources.raise_for_status()
            sites = resources.json()
        if sites:
            token_payload["cloud_id"] = sites[0]["id"]
            token_payload["site_url"] = sites[0].get("url")

    if provider == "microsoft_teams":
        # Best-effort: record which account connected (for display); non-fatal.
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                me = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {token_payload['access_token']}"},
                )
                if me.status_code == 200:
                    info = me.json()
                    token_payload["account"] = info.get("userPrincipalName") or info.get("mail")
        except Exception:
            pass

    return token_payload


async def _refresh_tokens(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = provider_oauth_config(provider)
    if not config or not payload.get("refresh_token"):
        raise ValueError(f"Cannot refresh {provider} token")

    async with httpx.AsyncClient(timeout=30) as client:
        body = {
            "grant_type": "refresh_token",
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "refresh_token": payload["refresh_token"],
        }
        resp = await client.post(
            config["token_url"],
            json=body if provider == "jira" else None,
            data=None if provider == "jira" else body,
        )
        resp.raise_for_status()
        data = resp.json()

    payload = dict(payload)
    payload["access_token"] = data["access_token"]
    if data.get("refresh_token"):
        payload["refresh_token"] = data["refresh_token"]
    if data.get("expires_in"):
        payload["expires_at"] = (datetime.now(UTC) + timedelta(seconds=int(data["expires_in"]))).isoformat()
    return payload


# --- token storage on the Integration row (encrypted at rest) ---

def store_tokens(integration: Integration, payload: dict[str, Any]) -> None:
    integration.encrypted_token = encrypt_secret(json.dumps(payload))
    integration.status = "connected"
    integration.scopes = payload.get("scope")
    if payload.get("expires_at"):
        integration.token_expires_at = datetime.fromisoformat(payload["expires_at"])


async def load_tokens(db: AsyncSession, workspace_id: str, provider: str) -> dict[str, Any] | None:
    """Load (and refresh if expired) the stored token payload for a workspace integration."""
    result = await db.execute(
        select(Integration).where(
            Integration.workspace_id == workspace_id,
            Integration.provider == provider,
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()
    if not integration or not integration.encrypted_token:
        return None
    try:
        payload = json.loads(decrypt_secret(integration.encrypted_token))
    except ValueError:
        _logger.error("Cannot decrypt %s token for workspace %s", provider, workspace_id)
        return None

    expires_at = payload.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now(UTC) + timedelta(minutes=2):
        try:
            payload = await _refresh_tokens(provider, payload)
            store_tokens(integration, payload)
            await db.flush()
        except Exception as exc:
            _logger.error("Token refresh failed for %s: %s", provider, exc)
            integration.status = "error"
            await db.flush()
            return None

    return payload


# --- real providers (same interface as the mocks) ---

class GoogleCalendarProvider:
    def __init__(self, access_token: str):
        self._token = access_token

    async def get_upcoming_events(self, workspace_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                params={
                    "timeMin": datetime.now(UTC).isoformat(),
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "maxResults": "10",
                },
                headers={"Authorization": f"Bearer {self._token}"},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
        return [
            {
                "id": e.get("id"),
                "title": e.get("summary", "(no title)"),
                "start": (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"),
                "end": (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date"),
                "attendees": [
                    {"name": a.get("displayName") or a.get("email", ""), "email": a.get("email", "")}
                    for a in e.get("attendees", [])
                ],
                "description": e.get("description"),
                "recurring": bool(e.get("recurringEventId")),
                # entryPoints can be present-but-empty (e.g. pending conference creation);
                # `or [{}]` covers both the missing-key and empty-list cases.
                "meet_link": ((e.get("conferenceData") or {}).get("entryPoints") or [{}])[0].get("uri"),
            }
            for e in items
        ]


class MicrosoftCalendarProvider:
    """Microsoft 365 / Outlook calendar via Microsoft Graph. Surfaces Teams join links."""

    def __init__(self, access_token: str):
        self._token = access_token

    async def get_upcoming_events(self, workspace_id: str) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        params = {
            "startDateTime": now.isoformat(),
            "endDateTime": (now + timedelta(days=30)).isoformat(),
            "$select": "subject,start,end,attendees,onlineMeeting,isOnlineMeeting,bodyPreview,type,seriesMasterId",
            "$orderby": "start/dateTime",
            "$top": "10",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/me/calendarView",
                params=params,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Prefer": 'outlook.timezone="UTC"',
                },
            )
            resp.raise_for_status()
            items = resp.json().get("value", [])
        return [
            {
                "id": e.get("id"),
                "title": e.get("subject", "(no title)"),
                "start": (e.get("start") or {}).get("dateTime"),
                "end": (e.get("end") or {}).get("dateTime"),
                "attendees": [
                    {
                        "name": (a.get("emailAddress") or {}).get("name", ""),
                        "email": (a.get("emailAddress") or {}).get("address", ""),
                    }
                    for a in e.get("attendees", [])
                ],
                "description": e.get("bodyPreview"),
                "recurring": e.get("type") == "occurrence" or bool(e.get("seriesMasterId")),
                "meet_link": (e.get("onlineMeeting") or {}).get("joinUrl"),
            }
            for e in items
        ]


class SlackProvider:
    def __init__(self, access_token: str):
        self._token = access_token

    async def send_message(self, channel: str, text: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                json={"channel": channel, "text": text},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        if not data.get("ok"):
            _logger.error("Slack send failed: %s", data.get("error"))
        return data

    async def send_dm(self, user_email: str, text: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            lookup = await client.get(
                "https://slack.com/api/users.lookupByEmail",
                params={"email": user_email},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            user = lookup.json()
        if not user.get("ok"):
            return {"ok": False, "error": user.get("error", "user_not_found")}
        return await self.send_message(user["user"]["id"], text)


class JiraProvider:
    def __init__(self, access_token: str, cloud_id: str):
        self._token = access_token
        self._base = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"

    async def get_tickets(self, workspace_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._base}/search",
                params={
                    "jql": "statusCategory != Done ORDER BY priority DESC, updated DESC",
                    "maxResults": "20",
                    "fields": "summary,status,assignee,priority,duedate,comment",
                },
                headers={"Authorization": f"Bearer {self._token}"},
            )
            resp.raise_for_status()
            issues = resp.json().get("issues", [])
        return [self._normalize(issue) for issue in issues]

    async def get_ticket(self, ticket_key: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self._base}/issue/{ticket_key}",
                params={"fields": "summary,status,assignee,priority,duedate,comment"},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return self._normalize(resp.json())

    async def update_ticket(self, ticket_key: str, updates: dict[str, Any]) -> dict[str, Any]:
        # Writes to Jira require explicit user review per product policy; only comments supported
        comment = updates.get("comment")
        if not comment:
            return {"key": ticket_key, "updated": False, "note": "Only comment updates are supported"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}/issue/{ticket_key}/comment",
                json={"body": {"type": "doc", "version": 1, "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": comment}]}
                ]}},
                headers={"Authorization": f"Bearer {self._token}"},
            )
            resp.raise_for_status()
        return {"key": ticket_key, "updated": True}

    @staticmethod
    def _adf_text(body: Any) -> str:
        """Best-effort extraction of plain text from a Jira ADF comment body.

        Each `content` level may be present-but-empty, so guard every index.
        """
        if not isinstance(body, dict):
            return str(body or "")
        top = body.get("content") or []
        if not top:
            return ""
        inner = (top[0].get("content") if isinstance(top[0], dict) else None) or []
        if not inner:
            return ""
        return (inner[0].get("text", "") if isinstance(inner[0], dict) else "") or ""

    @staticmethod
    def _normalize(issue: dict[str, Any]) -> dict[str, Any]:
        fields = issue.get("fields", {})
        comments = [
            JiraProvider._adf_text(c.get("body"))
            for c in (fields.get("comment") or {}).get("comments", [])[-3:]
        ]
        return {
            "key": issue.get("key"),
            "summary": fields.get("summary"),
            "status": (fields.get("status") or {}).get("name"),
            "assignee": (fields.get("assignee") or {}).get("displayName"),
            "priority": (fields.get("priority") or {}).get("name"),
            "sprint": None,
            "deadline": fields.get("duedate"),
            "comments": [c for c in comments if c],
            "blockers": [],
        }
