"""R1: Remember — wrap-time persistence, workspace open-items, prep-brief carryover,
and live nudges."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.meeting import ActionItem, Decision, Meeting, MeetingMode, Question
from app.models.speaking import SpeakingResponse
from app.models.user import Workspace, WorkspaceMember, WorkspaceRole


async def _make_meeting(db, workspace_id, title="Session"):
    m = Meeting(workspace_id=workspace_id, title=title, mode=MeetingMode.SHADOW)
    db.add(m)
    await db.flush()
    return m


def _mock_llm(json_return):
    inst = AsyncMock()
    inst.complete_json = AsyncMock(return_value=json_return)
    return inst


_EXTRACTION = {
    "commitments": [{"title": "Send the deck", "owner": "Test User", "deadline": "Friday"}],
    "actions": [{"title": "Update the Jira board", "owner": "Bob", "deadline": None}],
    "decisions": [{"text": "Ship v2 next sprint", "made_by": "Test User"}],
    "open_questions": [{"text": "Who owns the migration?", "asker": "Bob"}],
}


@pytest.mark.asyncio
async def test_speak_finalize_persists_open_items(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)
    db_session.add(SpeakingResponse(
        meeting_id=m.id, workspace_id=test_workspace.id,
        speaker="Bob", text="I'll update the Jira board, and you said you'd send the deck by Friday",
    ))
    await db_session.flush()

    summary = {"summary": "Done.", "action_items": [], "follow_ups": []}
    with (
        patch("app.services.speak_coverage.get_llm", return_value=_mock_llm(summary)),
        patch("app.services.commitments.get_llm", return_value=_mock_llm(_EXTRACTION)),
    ):
        r = await client.post(
            f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/speak/finalize", headers=h, json={}
        )
    assert r.status_code == 200, r.text

    items = (await db_session.execute(
        select(ActionItem).where(ActionItem.meeting_id == m.id)
    )).scalars().all()
    assert {(i.kind, i.title) for i in items} == {("commitment", "Send the deck"), ("action", "Update the Jira board")}
    assert all(i.source_context == "speak_wrap" and i.status == "open" for i in items)
    commitment = next(i for i in items if i.kind == "commitment")
    assert commitment.owner == "Test User" and commitment.deadline == "Friday"

    decisions = (await db_session.execute(
        select(Decision).where(Decision.meeting_id == m.id)
    )).scalars().all()
    assert [d.text for d in decisions] == ["Ship v2 next sprint"]
    assert decisions[0].source_context == "speak_wrap"

    questions = (await db_session.execute(
        select(Question).where(Question.meeting_id == m.id)
    )).scalars().all()
    assert [q.text for q in questions] == ["Who owns the migration?"]
    assert questions[0].status == "pending"
    assert questions[0].priority == "must_ask"
    assert questions[0].source_context == "carryover"


@pytest.mark.asyncio
async def test_report_regeneration_does_not_duplicate_rows(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)

    rep = {
        "summary": "Report summary", "follow_up_recommendations": [], "email_draft": "e",
        "slack_draft": "s", "jira_suggestions": [], "next_meeting_agenda": [],
        "commitments": [{"title": "Send pricing sheet", "owner": "Test User", "deadline": "Monday"}],
        "action_items": [{"title": "Fix login bug", "owner": "Sarah", "deadline": None}],
        "decisions": [{"text": "Go with option B", "made_by": "Sarah"}],
        "open_questions": [{"text": "What is the budget cap?", "asker": None}],
    }
    base = f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/reports/generate"
    with patch("app.services.report_generator.get_llm", return_value=_mock_llm(rep)):
        r1 = await client.post(base, headers=h)
        r2 = await client.post(base, headers=h)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    items = (await db_session.execute(
        select(ActionItem).where(ActionItem.meeting_id == m.id)
    )).scalars().all()
    assert {(i.kind, i.title) for i in items} == {("commitment", "Send pricing sheet"), ("action", "Fix login bug")}
    assert all(i.source_context == "report_wrap" for i in items)

    decisions = (await db_session.execute(
        select(Decision).where(Decision.meeting_id == m.id)
    )).scalars().all()
    assert [d.text for d in decisions] == ["Go with option B"]

    questions = (await db_session.execute(
        select(Question).where(Question.meeting_id == m.id)
    )).scalars().all()
    assert [q.text for q in questions] == ["What is the budget cap?"]
    assert questions[0].source_context == "report_wrap"


@pytest.mark.asyncio
async def test_open_items_is_workspace_scoped(client, auth_token, test_user, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    other_ws = Workspace(name="Other Workspace", slug="other-workspace-1")
    db_session.add(other_ws)
    await db_session.flush()
    db_session.add(WorkspaceMember(workspace_id=other_ws.id, user_id=test_user.id, role=WorkspaceRole.OWNER))
    m1 = await _make_meeting(db_session, test_workspace.id, title="Kickoff")
    m2 = await _make_meeting(db_session, other_ws.id, title="Elsewhere")

    db_session.add_all([
        ActionItem(meeting_id=m1.id, workspace_id=test_workspace.id, kind="commitment",
                   title="Send the deck", owner="Test User", deadline="Friday", source_context="speak_wrap"),
        ActionItem(meeting_id=m1.id, workspace_id=test_workspace.id, kind="action",
                   title="Update Jira", owner="Bob"),
        ActionItem(meeting_id=m1.id, workspace_id=test_workspace.id, kind="action",
                   title="Already done", status="done"),
        ActionItem(meeting_id=m2.id, workspace_id=other_ws.id, kind="commitment",
                   title="Other workspace promise"),
        Question(meeting_id=m1.id, workspace_id=test_workspace.id, text="Who owns the migration?",
                 source_context="carryover"),
        Question(meeting_id=m1.id, workspace_id=test_workspace.id, text="Resolved question",
                 status="answered"),
        Question(meeting_id=m2.id, workspace_id=other_ws.id, text="Other workspace question"),
    ])
    await db_session.flush()

    r = await client.get(f"/api/workspaces/{test_workspace.id}/open-items", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    assert [c["title"] for c in body["commitments"]] == ["Send the deck"]
    assert [a["title"] for a in body["actions"]] == ["Update Jira"]
    assert [q["text"] for q in body["questions"]] == ["Who owns the migration?"]

    c = body["commitments"][0]
    assert c["owner"] == "Test User" and c["deadline"] == "Friday" and c["status"] == "open"
    assert c["meeting_id"] == m1.id and c["meeting_title"] == "Kickoff"
    assert c["meeting_date"] and c["source_context"] == "speak_wrap"
    q = body["questions"][0]
    assert q["status"] == "pending" and q["meeting_title"] == "Kickoff" and q["source_context"] == "carryover"


@pytest.mark.asyncio
async def test_prep_brief_surfaces_commitments_from_previous_meetings(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    previous = await _make_meeting(db_session, test_workspace.id, title="Last week's sync")
    upcoming = await _make_meeting(db_session, test_workspace.id, title="This week's sync")

    db_session.add_all([
        ActionItem(meeting_id=previous.id, workspace_id=test_workspace.id, kind="commitment",
                   title="Send the deck", owner="Test User", deadline="Friday"),
        ActionItem(meeting_id=upcoming.id, workspace_id=test_workspace.id, kind="commitment",
                   title="Commitment from this meeting"),
        ActionItem(meeting_id=previous.id, workspace_id=test_workspace.id, kind="action",
                   title="Update Jira", owner="Bob"),
        Question(meeting_id=previous.id, workspace_id=test_workspace.id,
                 text="Who owns the migration?", source_context="carryover"),
    ])
    await db_session.flush()

    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/meetings/{upcoming.id}/prep-brief", headers=h
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Commitments come only from OTHER meetings.
    assert [c["title"] for c in body["commitments"]] == ["Send the deck"]
    c = body["commitments"][0]
    assert c["owner"] == "Test User" and c["deadline"] == "Friday"
    assert c["meeting_title"] == "Last week's sync" and c["meeting_date"]

    assert [q["text"] for q in body["open_questions"]] == ["Who owns the migration?"]
    assert body["open_questions"][0]["meeting_title"] == "Last week's sync"

    # Plain action items still populate their own list (and stay out of commitments).
    assert [a["title"] for a in body["open_action_items"]] == ["Update Jira"]


@pytest.mark.asyncio
async def test_ingest_returns_nudges_when_memory_matches(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    previous = await _make_meeting(db_session, test_workspace.id, title="Last week")
    live = await _make_meeting(db_session, test_workspace.id, title="Live now")
    promise = ActionItem(meeting_id=previous.id, workspace_id=test_workspace.id, kind="commitment",
                         title="Send the deck", owner="Test User")
    db_session.add(promise)
    await db_session.flush()

    nudge_payload = {"nudges": [
        {"kind": "promise", "item_id": promise.id, "text": "You promised to send the deck", "evidence": "the deck"},
        {"kind": "conflict", "item_id": "not-a-real-id", "text": "Contradicts a decision", "evidence": "..."},
        {"kind": "bogus-kind", "item_id": None, "text": "Should be dropped", "evidence": ""},
    ]}
    with patch("app.services.nudge_matcher.get_llm", return_value=_mock_llm(nudge_payload)):
        r = await client.post(
            f"/api/workspaces/{test_workspace.id}/meetings/{live.id}/speak/ingest",
            headers=h,
            json={"segments": [{"speaker": "You (mic)", "text": "About the deck we discussed"}]},
        )
    assert r.status_code == 200, r.text
    nudges = r.json()["nudges"]
    assert len(nudges) == 2
    assert nudges[0] == {
        "kind": "promise", "item_id": promise.id,
        "text": "You promised to send the deck", "evidence": "the deck",
    }
    assert nudges[1]["item_id"] is None  # unknown ids are nulled, not trusted


@pytest.mark.asyncio
async def test_ingest_skips_nudge_llm_when_no_open_items(client, auth_token, test_workspace, db_session):
    h = {"Authorization": f"Bearer {auth_token}"}
    m = await _make_meeting(db_session, test_workspace.id)

    with patch("app.services.nudge_matcher.get_llm") as nudge_llm:
        r = await client.post(
            f"/api/workspaces/{test_workspace.id}/meetings/{m.id}/speak/ingest",
            headers=h,
            json={"segments": [{"speaker": "You (mic)", "text": "Hello everyone"}]},
        )
    assert r.status_code == 200, r.text
    assert r.json()["nudges"] == []
    assert not nudge_llm.called
