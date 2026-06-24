from __future__ import annotations

import pytest

from app.models.meeting import Meeting, MeetingMode


async def _make_meeting(db, workspace_id):
    m = Meeting(workspace_id=workspace_id, title="Notetaker Meeting", mode=MeetingMode.SHADOW)
    db.add(m)
    await db.flush()
    return m


@pytest.mark.asyncio
async def test_notetaker_transcript_append_and_get(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    base = f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/notetaker"

    r = await client.post(f"{base}/transcript", headers=h, json={"segments": [
        {"speaker": "Alice", "text": "Let's review the roadmap."},
        {"speaker": "Bob", "text": "API is done, shipping Friday."},
    ]})
    assert r.status_code == 200
    assert r.json()["appended"] == 2

    # second append accumulates
    r = await client.post(f"{base}/transcript", headers=h, json={"segments": [
        {"speaker": "Alice", "text": "Great, what about the dashboard?"},
    ]})
    assert r.json()["total_lines"] == 3

    r = await client.get(f"{base}/transcript", headers=h)
    assert r.status_code == 200
    assert "API is done" in r.json()["transcript"]
    assert r.json()["lines"] == 3


@pytest.mark.asyncio
async def test_notetaker_notes_generation_graceful(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    base = f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/notetaker"

    # No transcript yet -> sensible empty notes
    r = await client.post(f"{base}/notes", headers=h)
    assert r.status_code == 200
    assert "No transcript" in r.json()["summary"]

    # With transcript -> notes structure present (LLM unavailable in tests -> graceful fallback)
    await client.post(f"{base}/transcript", headers=h, json={"segments": [
        {"speaker": "Bob", "text": "We will ship the release on Friday and Alice owns QA."},
    ]})
    r = await client.post(f"{base}/notes", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data and "action_items" in data


@pytest.mark.asyncio
async def test_notetaker_finalize_indexes_transcript(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    base = f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/notetaker"

    await client.post(f"{base}/transcript", headers=h, json={"segments": [
        {"speaker": "Carol", "text": "Deployment pipeline is stable now, owned by John."},
    ]})
    r = await client.post(f"{base}/finalize", headers=h)
    assert r.status_code == 200
    assert r.json()["finalized"] is True
    assert r.json()["chunks_indexed"] >= 1


@pytest.mark.asyncio
async def test_notetaker_requires_membership(client, auth_token, test_workspace, db_session):
    # A meeting in a workspace the user is NOT a member of -> 403/404
    import uuid

    from app.models.user import User, Workspace, WorkspaceMember, WorkspaceRole
    from app.core.security import hash_password

    other_uid = str(uuid.uuid4())
    other_wid = str(uuid.uuid4())
    db_session.add(User(id=other_uid, email=f"nt_{other_uid}@x.io", hashed_password=hash_password("x"), full_name="O"))
    db_session.add(Workspace(id=other_wid, name="Other", slug=f"other-{other_uid}"))
    db_session.add(WorkspaceMember(workspace_id=other_wid, user_id=other_uid, role=WorkspaceRole.OWNER))
    await db_session.flush()
    m = await _make_meeting(db_session, other_wid)

    r = await client.post(
        f"/api/workspaces/{other_wid}/meetings/{m.id}/notetaker/transcript",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"segments": [{"speaker": "X", "text": "secret"}]},
    )
    assert r.status_code in (403, 404)
