from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.meeting import Meeting, MeetingMode


async def _make_meeting(db, workspace_id):
    m = Meeting(workspace_id=workspace_id, title="Speak Session", mode=MeetingMode.SHADOW)
    db.add(m)
    await db.flush()
    return m


def _mock_llm(json_return):
    inst = AsyncMock()
    inst.complete_json = AsyncMock(return_value=json_return)
    return inst


@pytest.mark.asyncio
async def test_generate_points_from_text(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    base = f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/speak"

    gen = {"points": [
        {"text": "Welcome everyone", "stage": "Intro", "priority": "must"},
        {"text": "Q3 revenue up 20%", "stage": "Main", "priority": "should"},
        {"text": "Thank the team", "stage": "Close", "priority": "nice"},
    ]}
    with patch("app.services.speak_coverage.get_llm", return_value=_mock_llm(gen)):
        r = await client.post(f"{base}/points/generate", headers=h, json={"text": "welcome; q3 revenue; thanks"})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["progress"]["total"] == 3
    assert st["progress"]["must_remaining"] == 1
    assert st["points"][0]["stage"] == "Intro"


@pytest.mark.asyncio
async def test_ingest_marks_points_covered_and_captures_responses(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    base = f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/speak"

    gen = {"points": [
        {"text": "Welcome everyone", "stage": "Intro", "priority": "must"},
        {"text": "Q3 revenue up 20%", "stage": "Main", "priority": "must"},
    ]}
    with patch("app.services.speak_coverage.get_llm", return_value=_mock_llm(gen)):
        r = await client.post(f"{base}/points/generate", headers=h, json={"text": "..."})
    point_ids = [p["id"] for p in r.json()["points"]]

    # Speaker covers the first point; a participant asks a question.
    match = {
        "covered": [{"id": point_ids[0], "evidence": "Hi everyone, welcome"}],
        "responses": [{"speaker": "Bob", "text": "What drove the growth?", "kind": "question", "point_id": point_ids[1]}],
    }
    with patch("app.services.speak_coverage.get_llm", return_value=_mock_llm(match)):
        r = await client.post(f"{base}/ingest", headers=h, json={"segments": [
            {"speaker": "You (mic)", "text": "Hi everyone, welcome to the call"},
            {"speaker": "Bob", "text": "What drove the growth?"},
        ]})
    assert r.status_code == 200, r.text
    st = r.json()
    assert point_ids[0] in st["newly_covered"]
    assert st["progress"]["covered"] == 1
    assert st["progress"]["must_remaining"] == 1  # second must-point still pending
    assert any(x["kind"] == "question" for x in st["responses"])


@pytest.mark.asyncio
async def test_finalize_marks_missed_and_summarizes(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    base = f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/speak"

    gen = {"points": [{"text": "Point A", "stage": "Main", "priority": "must"}, {"text": "Point B", "stage": "Main", "priority": "should"}]}
    with patch("app.services.speak_coverage.get_llm", return_value=_mock_llm(gen)):
        await client.post(f"{base}/points/generate", headers=h, json={"text": "..."})

    summary = {"summary": "Covered A, missed B.", "action_items": [{"title": "Send deck", "owner": None}], "follow_ups": ["Cover Point B next time"]}
    with patch("app.services.speak_coverage.get_llm", return_value=_mock_llm(summary)):
        r = await client.post(f"{base}/finalize", headers=h, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"] == "Covered A, missed B."
    assert "Point A" in body["missed"] and "Point B" in body["missed"]  # both pending -> missed
    assert body["action_items"][0]["title"] == "Send deck"

    # State now reflects missed.
    r = await client.get(f"{base}/state", headers=h)
    assert r.json()["progress"]["missed"] == 2


@pytest.mark.asyncio
async def test_share_report_exposes_public_recap(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    base = f"/api/workspaces/{test_workspace.id}/meetings/{m.id}"

    gen = {"points": [{"text": "Point A", "stage": "Main", "priority": "must"}]}
    with patch("app.services.speak_coverage.get_llm", return_value=_mock_llm(gen)):
        await client.post(f"{base}/speak/points/generate", headers=h, json={"text": "..."})

    summary = {"summary": "Great session.", "action_items": [], "follow_ups": []}
    with patch("app.services.speak_coverage.get_llm", return_value=_mock_llm(summary)):
        fin = await client.post(f"{base}/speak/finalize", headers=h, json={})
    report_id = fin.json()["report_id"]

    # Create the public share link.
    r = await client.post(f"{base}/reports/{report_id}/share", headers=h)
    assert r.status_code == 200, r.text
    token = r.json()["share_token"]
    assert token and "/r/" in r.json()["url"]

    # Public recap is reachable WITHOUT auth and shows the shared content.
    pub = await client.get(f"/api/public/reports/{token}")
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["summary"] == "Great session."
    assert body["missed"] == ["Point A"]

    # Revoking makes the link 404.
    await client.delete(f"{base}/reports/{report_id}/share", headers=h)
    gone = await client.get(f"/api/public/reports/{token}")
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_public_recap_unknown_token_404(client):
    r = await client.get("/api/public/reports/this-token-does-not-exist-000000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_generate_requires_input(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/speak/points/generate",
        headers=h, json={},
    )
    assert r.status_code == 400
