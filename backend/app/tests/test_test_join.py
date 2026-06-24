from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_test_join_rejects_mock_provider(client, auth_token, test_workspace):
    # Default test env uses the mock bot provider -> the real-only guard must reject.
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/test-join",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"meeting_url": "https://meet.ffmuc.net/Room", "when": "now", "mode": "recorder"},
    )
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_test_join_validates_url(client, auth_token, test_workspace, monkeypatch):
    # Pretend a real provider is configured so we pass the guard and hit URL validation.
    from app.routers import live_session

    monkeypatch.setattr(live_session._settings, "bot_provider", "browser")
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/test-join",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"meeting_url": "not-a-url", "when": "now", "mode": "recorder"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_test_join_rejects_bad_when(client, auth_token, test_workspace, monkeypatch):
    from app.routers import live_session

    monkeypatch.setattr(live_session._settings, "bot_provider", "browser")
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/test-join",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"meeting_url": "https://meet.ffmuc.net/Room", "when": "not-a-time", "mode": "recorder"},
    )
    assert r.status_code == 400
