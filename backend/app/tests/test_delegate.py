from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

from app.models.delegate import DelegateSession
from app.models.meeting import Meeting, MeetingMode, Question, QuestionStatus, Report
from app.models.speaking import SpeakingPoint
from app.models.user import AuditLog, UsageRecord, User, Workspace
from app.services import delegate_engine as de
from app.services import report_generator
from app.services.meeting_bot import MockMeetingBotProvider
from app.services.meeting_bot.base import TranscriptSegment


class _FakeTTS:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return b"\x00" * 64


class _FakeLLM:
    async def complete_json(self, system: str, user: str) -> dict:
        return {"directed_at_owner": True, "reason": "question names the owner"}


class _SpyBotProvider(MockMeetingBotProvider):
    def __init__(self) -> None:
        self.left: list[str] = []
        self.audio_out: list[str] = []

    async def leave_meeting(self, bot_id: str) -> bool:
        self.left.append(bot_id)
        return True

    async def output_audio(self, bot_id: str, mp3_bytes: bytes) -> bool:
        self.audio_out.append(bot_id)
        return True


_REPORT_LLM_RESULT = {
    "summary": "Delegate recap.",
    "follow_up_recommendations": [],
    "email_draft": "email",
    "slack_draft": "slack",
    "jira_suggestions": [],
    "next_meeting_agenda": [],
    "commitments": [],
    "action_items": [],
    "decisions": [],
    "open_questions": [],
}


def _patch_report_llm(monkeypatch) -> AsyncMock:
    llm = AsyncMock()
    llm.complete_json = AsyncMock(return_value=_REPORT_LLM_RESULT)
    monkeypatch.setattr(report_generator, "get_llm", lambda: llm)
    return llm


def _seg(speaker: str, text: str, ts: int = 1000, final: bool = True) -> TranscriptSegment:
    return TranscriptSegment(speaker=speaker, text=text, timestamp_ms=ts, is_final=final)


async def _make_agent(db, workspace, stage: str, owner: str = "Alex Example"):
    meeting = Meeting(
        workspace_id=workspace.id,
        title="Delegate test",
        mode=MeetingMode.PROXY,
        proxy_consent_given=True,
        meeting_url="https://zoom.us/j/delegate",
    )
    db.add(meeting)
    await db.flush()
    session = DelegateSession(
        meeting_id=meeting.id,
        workspace_id=workspace.id,
        stage=stage,
        consent_recorded_at=datetime.now(UTC),
    )
    db.add(session)
    await db.flush()
    agent = de.DelegateAgent(db=db, meeting=meeting, session=session, owner_name=owner)
    agent._tts = _FakeTTS()
    agent._llm = _FakeLLM()
    agent._bot_provider = _SpyBotProvider()
    return meeting, session, agent


async def _drive(agent, segments: list[TranscriptSegment], stop: bool = True) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def _consume() -> None:
        async for e in agent.run():
            events.append(e)

    task = asyncio.create_task(_consume())
    for _ in range(200):  # wait for the bot to be verified in-meeting
        if agent._session.status in ("active", "done", "error") or task.done():
            break
        await asyncio.sleep(0.05)
    for seg in segments:
        await agent.ingest_transcript_segment(seg)
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.5)  # let the listen loop drain before stopping
    if stop:
        agent.stop()
    await asyncio.wait_for(task, timeout=30)
    return events


async def _audit_rows(db, session_id: str, action: str) -> list[AuditLog]:
    return list((await db.execute(
        select(AuditLog).where(
            AuditLog.action == action,
            AuditLog.resource_type == "delegate_session",
            AuditLog.resource_id == session_id,
        ).order_by(AuditLog.created_at)
    )).scalars().all())


# ── (a) Stage A: silent delegate ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_a_discloses_records_and_reports(db_session, test_workspace, monkeypatch):
    _patch_report_llm(monkeypatch)
    meeting, session, agent = await _make_agent(db_session, test_workspace, "silent")

    events = await _drive(agent, [
        _seg("Sarah Chen", "Welcome everyone, let's start."),
        _seg("David Lee", "The rollout is on track for Friday."),
    ])
    types = [e["type"] for e in events]

    assert "disclosure" in types
    disclosure = next(e for e in events if e["type"] == "disclosure")
    assert "AI delegate" in disclosure["text"] and "drop the bot" in disclosure["text"]
    assert session.status == "done"
    assert session.bot_id
    assert session.disclosure_logged_at is not None

    disc_rows = await _audit_rows(db_session, session.id, "delegate.disclosure")
    assert len(disc_rows) == 1 and disc_rows[0].created_at is not None
    utterances = await _audit_rows(db_session, session.id, "delegate.utterance")
    assert len(utterances) == 1  # the disclosure — a silent delegate never speaks again
    assert json.loads(utterances[0].detail)["text"] == disclosure["text"]
    assert agent._tts.spoken == [disclosure["text"]]

    # transcript ingested via the shared bot plumbing
    assert agent._db_bot is not None
    assert "rollout" in (agent._db_bot.transcript_json or "")

    # report merged with the delegate audit trail
    report = (await db_session.execute(select(Report).where(Report.meeting_id == meeting.id))).scalar_one()
    full = json.loads(report.full_json)
    assert [u["text"] for u in full["delegate_utterances"]] == [disclosure["text"]]
    assert all(u["ts"] for u in full["delegate_utterances"])
    assert full["delegate_follow_ups"] == []

    usage = (await db_session.execute(
        select(UsageRecord).where(
            UsageRecord.workspace_id == test_workspace.id,
            UsageRecord.metric == "delegate_sessions",
        )
    )).scalar_one()
    assert usage.count == 1


@pytest.mark.asyncio
async def test_stage_a_with_tts_none_still_audits_disclosure(db_session, test_workspace, monkeypatch):
    _patch_report_llm(monkeypatch)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tts_provider", "none")
    _, session, agent = await _make_agent(db_session, test_workspace, "silent")

    await _drive(agent, [_seg("Sarah Chen", "Quick sync today.")])

    assert session.status == "done"
    utterances = await _audit_rows(db_session, session.id, "delegate.utterance")
    assert len(utterances) == 1
    detail = json.loads(utterances[0].detail)
    assert detail["kind"] == "disclosure"
    assert detail["tts"] == "tts_unavailable"


# ── (b) Stage B: briefed delegate ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_stage_b_delivers_script_and_captures_follow_ups(db_session, test_workspace, monkeypatch):
    _patch_report_llm(monkeypatch)
    meeting, session, agent = await _make_agent(db_session, test_workspace, "briefed", owner="Alex Example")

    db_session.add_all([
        SpeakingPoint(meeting_id=meeting.id, workspace_id=test_workspace.id,
                      text="Ship date moved to Friday.", priority="must", order_index=2),
        SpeakingPoint(meeting_id=meeting.id, workspace_id=test_workspace.id,
                      text="Design review is complete.", priority="should", order_index=1),
        SpeakingPoint(meeting_id=meeting.id, workspace_id=test_workspace.id,
                      text="We hired a new tester.", priority="nice", order_index=3),
    ])
    q_allowed = Question(meeting_id=meeting.id, workspace_id=test_workspace.id,
                         text="What is blocking the launch?", proxy_allowed=True)
    q_private = Question(meeting_id=meeting.id, workspace_id=test_workspace.id,
                         text="Internal-only question.", proxy_allowed=False)
    db_session.add_all([q_allowed, q_private])
    await db_session.flush()

    events = await _drive(agent, [
        _seg("David Lee", "When is the deck due, Alex?", ts=2000),
        _seg("Priya Patel", "Alex, can you approve the extra budget?", ts=3000),
        _seg("Priya Patel", "And Alex, can you sign the contract today?", ts=4000),
        _seg("Sarah Chen", "Thanks, moving on."),
    ])

    # Script composed at start: must-priority first, then order_index; approved questions only
    script = json.loads(session.script_json)
    assert [u["text"] for u in script["updates"]] == [
        "Ship date moved to Friday.", "Design review is complete.", "We hired a new tester.",
    ]
    assert [q["text"] for q in script["questions"]] == ["What is blocking the launch?"]

    # Every utterance audit-logged: disclosure + 3 updates + 1 question + 1 never-commit line
    utterances = await _audit_rows(db_session, session.id, "delegate.utterance")
    kinds = [json.loads(u.detail)["kind"] for u in utterances]
    assert kinds == ["disclosure", "script_update", "script_update", "script_update",
                     "script_question", "never_commit"]
    assert agent._tts.spoken == [json.loads(u.detail)["text"] for u in utterances]

    # The never-commit deferral is spoken at most once, despite two restricted asks
    reply = next(e for e in events if e["type"] == "delegate_reply")
    assert "check with Alex Example" in reply["text"]
    assert kinds.count("never_commit") == 1

    assert q_allowed.status == QuestionStatus.ASKED
    assert q_private.status == QuestionStatus.PENDING

    follow_ups = json.loads(session.follow_ups_json)
    assert len(follow_ups) == 3
    assert follow_ups[0] == {"asker": "David Lee", "text": "When is the deck due, Alex?", "ts": 2000}

    report = (await db_session.execute(select(Report).where(Report.meeting_id == meeting.id))).scalar_one()
    full = json.loads(report.full_json)
    assert full["delegate_follow_ups"] == follow_ups
    assert len(full["delegate_utterances"]) == 6


# ── (c) Kill switch ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kill_switch_ejects_the_delegate(db_session, test_workspace, monkeypatch):
    _patch_report_llm(monkeypatch)
    _, session, agent = await _make_agent(db_session, test_workspace, "silent")

    events = await _drive(agent, [
        _seg("Sarah Chen", "Please DROP the bot right now."),
    ], stop=False)

    assert session.status == "done"
    kill_rows = await _audit_rows(db_session, session.id, "delegate.kill_switch")
    assert len(kill_rows) == 1 and "Sarah Chen" in kill_rows[0].detail
    # Speaks nothing on eject — only the disclosure was ever uttered
    utterances = await _audit_rows(db_session, session.id, "delegate.utterance")
    assert len(utterances) == 1
    assert agent._bot_provider.left  # provider.leave_meeting was called
    status_events = [e for e in events if e["type"] == "delegate_status"]
    assert any(e.get("reason") == "kill_switch" for e in status_events)


# ── Router: gates and shapes ───────────────────────────────────────────────


async def _make_meeting(db, workspace_id: str, **kwargs) -> Meeting:
    meeting = Meeting(workspace_id=workspace_id, title="Delegate endpoint test",
                      mode=MeetingMode.PROXY, **kwargs)
    db.add(meeting)
    await db.flush()
    return meeting


@pytest.mark.asyncio
async def test_delegate_start_requires_consent(client, auth_token, db_session, test_workspace):
    meeting = await _make_meeting(db_session, test_workspace.id,
                                  proxy_consent_given=False, meeting_url="https://zoom.us/j/1")
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/{meeting.id}/delegate/start",
        json={"stage": "silent"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 403
    assert "consent" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delegate_start_rejects_invalid_stage(client, auth_token, db_session, test_workspace):
    meeting = await _make_meeting(db_session, test_workspace.id,
                                  proxy_consent_given=True, meeting_url="https://zoom.us/j/1")
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/{meeting.id}/delegate/start",
        json={"stage": "interactive"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_delegate_briefed_requires_tts(client, auth_token, db_session, test_workspace, monkeypatch):
    from app.routers import delegate as delegate_router

    monkeypatch.setattr(delegate_router._settings, "tts_provider", "none")
    meeting = await _make_meeting(db_session, test_workspace.id,
                                  proxy_consent_given=True, meeting_url="https://zoom.us/j/1")
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/{meeting.id}/delegate/start",
        json={"stage": "briefed"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 422
    assert "requires TTS" in r.json()["detail"]
    # Refused BEFORE joining: no session row was created
    rows = (await db_session.execute(
        select(DelegateSession).where(DelegateSession.meeting_id == meeting.id)
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_delegate_start_mock_provider_needs_meeting_url(client, auth_token, db_session, test_workspace):
    meeting = await _make_meeting(db_session, test_workspace.id, proxy_consent_given=True)
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/{meeting.id}/delegate/start",
        json={"stage": "silent"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 503


class _FakeAgent:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_delegate_start_status_stop_and_double_start(
    client, auth_token, db_session, test_user, test_workspace, monkeypatch,
):
    """Successful start (launch patched) -> 409 on double start -> status/stop shapes.

    The start endpoint commits, so this test cleans up its committed fixtures at the
    end to preserve the rollback isolation the rest of the suite relies on."""
    from app.routers import delegate as delegate_router

    fake_agent = _FakeAgent()
    launched: dict[str, Any] = {}

    async def _fake_launch(session_id, meeting_id, workspace_id, owner_name):
        launched.update(session_id=session_id, meeting_id=meeting_id, owner_name=owner_name)
        de._active_delegates[meeting_id] = fake_agent

    monkeypatch.setattr(delegate_router, "launch_delegate", _fake_launch)
    # Plain-string ids: the cleanup rollback expires ORM objects, and expired
    # attribute access outside a greenlet context raises.
    wid, uid = test_workspace.id, test_user.id
    meeting = await _make_meeting(db_session, wid,
                                  proxy_consent_given=True, meeting_url="https://zoom.us/j/1")
    mid = meeting.id
    headers = {"Authorization": f"Bearer {auth_token}"}
    base = f"/api/workspaces/{wid}/meetings/{mid}/delegate"

    try:
        r = await client.post(f"{base}/start", json={"stage": "silent"}, headers=headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "started"
        sess = data["session"]
        assert sess["stage"] == "silent" and sess["status"] == "created"
        assert sess["consent_recorded_at"] is not None
        assert sess["follow_ups"] == [] and sess["script"] is None
        assert launched["session_id"] == sess["id"]
        assert launched["owner_name"] == "Test User"

        r2 = await client.post(f"{base}/start", json={"stage": "silent"}, headers=headers)
        assert r2.status_code == 409

        r3 = await client.get(f"{base}/status", headers=headers)
        assert r3.status_code == 200
        st = r3.json()
        assert st["id"] == sess["id"] and st["active"] is True and st["follow_ups"] == []

        r4 = await client.post(f"{base}/stop", headers=headers)
        assert r4.status_code == 200 and r4.json()["status"] == "stopping"
        assert fake_agent.stopped
    finally:
        de._active_delegates.pop(mid, None)
        await db_session.rollback()
        await db_session.execute(delete(AuditLog).where(AuditLog.workspace_id == wid))
        await db_session.execute(delete(Workspace).where(Workspace.id == wid))
        await db_session.execute(delete(User).where(User.id == uid))
        await db_session.commit()


@pytest.mark.asyncio
async def test_delegate_stop_and_status_without_session(client, auth_token, db_session, test_workspace):
    meeting = await _make_meeting(db_session, test_workspace.id, proxy_consent_given=True)
    headers = {"Authorization": f"Bearer {auth_token}"}
    base = f"/api/workspaces/{test_workspace.id}/meetings/{meeting.id}/delegate"

    r = await client.post(f"{base}/stop", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "not_running"

    r = await client.get(f"{base}/status", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "no_delegate"
