from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.models.meeting import Meeting, MeetingMode, MeetingStatus


# ── Recall.ai bot: real output_audio + automatic_audio_output ──────────────

def _recall_provider_with_transport(handler):
    """Build a RecallAIBotProvider whose HTTP client is backed by a MockTransport."""
    from app.services.meeting_bot import recall as recall_mod

    recall_mod._settings.recall_api_key = "test-key"
    provider = recall_mod.RecallAIBotProvider()
    provider._client = httpx.AsyncClient(
        base_url="https://recall.test/api/v1/",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Token test-key"},
    )
    return provider


@pytest.mark.asyncio
async def test_recall_output_audio_posts_real_endpoint_shape():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    provider = _recall_provider_with_transport(handler)
    ok = await provider.output_audio("bot-123", b"\x00\x01fake-mp3-bytes")

    assert ok is True
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/bot/bot-123/output_audio/")
    assert captured["body"]["kind"] == "mp3"
    # b64_data must be valid base64 of the bytes we passed
    import base64
    assert base64.b64decode(captured["body"]["b64_data"]) == b"\x00\x01fake-mp3-bytes"


@pytest.mark.asyncio
async def test_recall_create_bot_enables_audio_output():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "bot-xyz", "status_changes": []})

    provider = _recall_provider_with_transport(handler)
    info = await provider.create_bot("https://zoom.us/j/123", bot_name="AmMeeting")

    assert info.bot_id == "bot-xyz"
    # The bot must be created with automatic_audio_output so /output_audio/ works
    aao = captured["body"].get("automatic_audio_output")
    assert aao is not None
    assert aao["in_call_recording"]["data"]["kind"] == "mp3"
    assert aao["in_call_recording"]["data"]["b64_data"]  # non-empty silent mp3


def test_mock_bot_has_output_audio_not_speak_message():
    from app.services.meeting_bot import MockMeetingBotProvider

    p = MockMeetingBotProvider()
    assert hasattr(p, "output_audio")
    assert not hasattr(p, "speak_message")


# ── Self-hosted browser bot provider (drives the bot-worker) ────────────────

def _browser_provider_with_transport(handler):
    import app.services.meeting_bot.browser as bmod

    provider = bmod.BrowserBotProvider()
    real_client = httpx.AsyncClient
    bmod.httpx.AsyncClient = lambda *a, **k: real_client(transport=httpx.MockTransport(handler))
    return provider, bmod, real_client


@pytest.mark.asyncio
async def test_browser_bot_create_join_speak_leave():
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.content))
        path = request.url.path
        if request.method == "POST" and path == "/bots":
            body = json.loads(request.content)
            assert body["meeting_url"].startswith("https://")
            assert body["webhook_url"].endswith("/api/webhooks/recall/m1")
            return httpx.Response(201, json={"id": "bot-1", "status": "joining", "platform": "jitsi"})
        if request.method == "GET" and path == "/bots/bot-1":
            return httpx.Response(200, json={"id": "bot-1", "status": "in_meeting", "segments": 2})
        if path == "/bots/bot-1/output-audio":
            assert json.loads(request.content)["b64"]
            return httpx.Response(200, json={"ok": True})
        if path == "/bots/bot-1/transcript":
            return httpx.Response(200, json={"segments": [
                {"speaker": "Dave", "text": "Status looks good", "timestamp_ms": 1},
            ]})
        if path == "/bots/bot-1/leave":
            return httpx.Response(200, json={"status": "left"})
        return httpx.Response(404, json={})

    provider, bmod, real = _browser_provider_with_transport(handler)
    try:
        info = await provider.create_bot("https://meet.ffmuc.net/room", "AmMeeting",
                                         webhook_url="http://localhost:8010/api/webhooks/recall/m1")
        assert info.bot_id == "bot-1" and info.provider == "browser"

        status = await provider.get_bot_status("bot-1")
        assert str(status.status) == "in_meeting" or status.status.value == "in_meeting"

        assert await provider.output_audio("bot-1", b"fake-mp3") is True

        segs = await provider.get_transcript("bot-1")
        assert segs[0].speaker == "Dave" and "Status" in segs[0].text

        assert await provider.leave_meeting("bot-1") is True
    finally:
        bmod.httpx.AsyncClient = real

    paths = [p for _, p, _ in calls]
    assert "/bots" in paths and "/bots/bot-1/leave" in paths


def test_browser_provider_selected_by_factory(monkeypatch):
    from app.core.config import get_settings
    from app.services.meeting_bot import get_bot_provider
    from app.services.meeting_bot.browser import BrowserBotProvider

    monkeypatch.setattr(get_settings(), "bot_provider", "browser")
    assert isinstance(get_bot_provider(), BrowserBotProvider)


# ── Microsoft Teams / 365 integration ──────────────────────────────────────

def test_microsoft_is_oauth_capable_provider():
    from app.routers.integrations import OAUTH_PROVIDERS

    assert "microsoft_teams" in OAUTH_PROVIDERS


def test_microsoft_oauth_config_requires_creds(monkeypatch):
    from app.services.integrations import oauth_providers as op

    # No creds -> not configured (stays mock)
    monkeypatch.setattr(op._settings, "microsoft_client_id", "")
    monkeypatch.setattr(op._settings, "microsoft_client_secret", "")
    assert op.provider_oauth_config("microsoft_teams") is None

    # With creds -> a real config + auth URL
    monkeypatch.setattr(op._settings, "microsoft_client_id", "ms-client")
    monkeypatch.setattr(op._settings, "microsoft_client_secret", "ms-secret")
    cfg = op.provider_oauth_config("microsoft_teams")
    assert cfg is not None
    assert "login.microsoftonline.com" in cfg["auth_url"]
    url = op.build_auth_url("microsoft_teams", state="xyz")
    assert url and "client_id=ms-client" in url and "state=xyz" in url


@pytest.mark.asyncio
async def test_microsoft_calendar_normalizes_teams_join_link():
    import httpx

    from app.services.integrations.oauth_providers import MicrosoftCalendarProvider

    graph_event = {
        "id": "evt1",
        "subject": "Teams Sync",
        "start": {"dateTime": "2026-06-22T10:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-06-22T11:00:00.0000000", "timeZone": "UTC"},
        "attendees": [{"emailAddress": {"name": "Sam Lee", "address": "sam@contoso.com"}}],
        "bodyPreview": "Weekly sync",
        "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/abc"},
        "isOnlineMeeting": True,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "calendarView" in str(request.url)
        return httpx.Response(200, json={"value": [graph_event]})

    provider = MicrosoftCalendarProvider("fake-token")
    import app.services.integrations.oauth_providers as mod
    real_client = httpx.AsyncClient
    mod.httpx.AsyncClient = lambda *a, **k: real_client(transport=httpx.MockTransport(handler))
    try:
        events = await provider.get_upcoming_events("ws")
    finally:
        mod.httpx.AsyncClient = real_client

    assert events[0]["title"] == "Teams Sync"
    assert events[0]["meet_link"] == "https://teams.microsoft.com/l/meetup-join/abc"
    assert events[0]["attendees"][0]["email"] == "sam@contoso.com"


@pytest.mark.asyncio
async def test_microsoft_connect_is_mock_without_creds(client, auth_token, test_workspace):
    # No Microsoft creds in tests -> connecting falls back to mock connection
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/integrations/microsoft_teams/connect",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "connected"
    assert r.json()["auth_url"] is None


# ── Calendar events endpoint ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_events_endpoint(client, auth_token, test_workspace):
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/calendar/events",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    events = r.json()
    assert isinstance(events, list)
    # mock provider returns at least one fixture event with attendees
    assert events and "title" in events[0] and "attendees" in events[0]


# ── Meeting create accepts calendar / auto-join fields ─────────────────────

@pytest.mark.asyncio
async def test_create_meeting_with_calendar_and_autojoin(client, auth_token, test_workspace):
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings",
        json={
            "title": "Calendar Synced Meeting",
            "mode": "proxy",
            "meeting_url": "https://zoom.us/j/999",
            "calendar_event_id": "cal_001",
            "auto_join_enabled": True,
            "proxy_consent_given": True,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["meeting_url"] == "https://zoom.us/j/999"
    assert data["calendar_event_id"] == "cal_001"
    assert data["auto_join_enabled"] is True
    # Consent must persist from create (otherwise proxy join/auto-join is blocked)
    assert data["proxy_consent_given"] is True


# ── Auto-join scheduler selection ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_dispatches_due_meeting(monkeypatch):
    """A due proxy meeting with consent + URL + auto-join is dispatched exactly once.

    Fully self-contained (own workspace/owner, committed + cleaned up) so it does
    not break the rollback isolation other tests rely on.
    """
    import uuid

    from sqlalchemy import delete

    from app.core.security import hash_password
    from app.models.user import User, Workspace, WorkspaceMember, WorkspaceRole
    from app.services import scheduler
    from app.tests.conftest import TestSession

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", TestSession)
    launched: list[dict] = []

    async def _fake_launch(**kwargs):
        launched.append(kwargs)

    monkeypatch.setattr(scheduler, "launch_session", _fake_launch)

    uid, wid = str(uuid.uuid4()), str(uuid.uuid4())
    due_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    async with TestSession() as s:
        s.add(User(id=uid, email=f"sched_{uid}@x.io", hashed_password=hash_password("x"), full_name="Sched Owner"))
        s.add(Workspace(id=wid, name="Sched WS", slug=f"sched-{uid}"))
        s.add(WorkspaceMember(workspace_id=wid, user_id=uid, role=WorkspaceRole.OWNER))
        await s.flush()  # ensure workspace exists before meetings (FK)
        common = dict(workspace_id=wid, mode=MeetingMode.PROXY, status=MeetingStatus.READY,
                      proxy_consent_given=True, auto_join_enabled=True)
        s.add(Meeting(id=due_id, title="Due", meeting_url="https://zoom.us/j/due", scheduled_at=now, **common))
        s.add(Meeting(id=str(uuid.uuid4()), title="Future", meeting_url="https://zoom.us/j/future",
                      scheduled_at=now + timedelta(hours=2), **common))
        s.add(Meeting(id=str(uuid.uuid4()), title="NoConsent", meeting_url="https://zoom.us/j/nc",
                      scheduled_at=now, **{**common, "proxy_consent_given": False}))
        await s.commit()

    try:
        n = await scheduler.scan_and_dispatch()
        assert n == 1
        assert len(launched) == 1
        assert launched[0]["meeting_id"] == due_id
        assert launched[0]["meeting_url"] == "https://zoom.us/j/due"

        # Dispatched flag set -> a second scan does NOT re-dispatch
        launched.clear()
        assert await scheduler.scan_and_dispatch() == 0
        assert launched == []
    finally:
        async with TestSession() as s:
            await s.execute(delete(Meeting).where(Meeting.workspace_id == wid))
            await s.execute(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == wid))
            await s.execute(delete(Workspace).where(Workspace.id == wid))
            await s.execute(delete(User).where(User.id == uid))
            await s.commit()
