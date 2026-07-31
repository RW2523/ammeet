from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.models.delegate import ApprovalRequest, DelegateSession
from app.models.meeting import Meeting, MeetingMode
from app.models.user import AuditLog, User, Workspace
from app.services import delegate_engine as de
from app.services import notify, report_generator
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


class _FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def send(self, title: str, body: str, click_url: str) -> None:
        self.calls.append({"title": title, "body": body, "click_url": click_url})


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

_PROPOSED_ANSWER = "The rollout ships Friday; the pipeline fix is owned by John."
_KB_CHUNKS = [SimpleNamespace(id="chunk-1", source_type="transcript", meeting_id="m-prev")]


def _patch_report_llm(monkeypatch) -> None:
    llm = AsyncMock()
    llm.complete_json = AsyncMock(return_value=_REPORT_LLM_RESULT)
    monkeypatch.setattr(report_generator, "get_llm", lambda: llm)


def _patch_interactive(monkeypatch, timeout_s: int) -> AsyncMock:
    """Enable stage C plumbing: fast approvals window, non-restricted escalation
    verdicts, and a mocked KB answer path. Returns the RAG mock."""
    _patch_report_llm(monkeypatch)
    monkeypatch.setattr(get_settings(), "approval_timeout_seconds", timeout_s)
    monkeypatch.setattr(de, "classify_escalation", AsyncMock(return_value={"requires_escalation": False}))
    rag = AsyncMock(return_value=(_PROPOSED_ANSWER, list(_KB_CHUNKS)))
    monkeypatch.setattr(de, "answer_from_knowledge", rag)
    return rag


def _seg(speaker: str, text: str, ts: int = 1000, final: bool = True) -> TranscriptSegment:
    return TranscriptSegment(speaker=speaker, text=text, timestamp_ms=ts, is_final=final)


@pytest_asyncio.fixture
async def iws(db_session):
    """Throwaway workspace (unique slug) — the agent and the decision endpoint
    COMMIT, so committed rows are deleted afterwards to keep suite isolation."""
    ws = Workspace(name="Interactive WS", slug=f"interactive-{uuid.uuid4().hex[:10]}")
    db_session.add(ws)
    await db_session.flush()
    wid = ws.id
    yield ws
    await db_session.rollback()
    await db_session.execute(delete(AuditLog).where(AuditLog.workspace_id == wid))
    await db_session.execute(delete(Workspace).where(Workspace.id == wid))
    await db_session.commit()


async def _make_agent(db, workspace, owner: str = "Alex Example"):
    meeting = Meeting(
        workspace_id=workspace.id,
        title="Interactive delegate test",
        mode=MeetingMode.PROXY,
        proxy_consent_given=True,
        meeting_url="https://zoom.us/j/interactive",
    )
    db.add(meeting)
    await db.flush()
    session = DelegateSession(
        meeting_id=meeting.id,
        workspace_id=workspace.id,
        stage="interactive",
        consent_recorded_at=datetime.now(UTC),
    )
    db.add(session)
    await db.flush()
    agent = de.DelegateAgent(db=db, meeting=meeting, session=session, owner_name=owner)
    agent._tts = _FakeTTS()
    agent._llm = _FakeLLM()
    agent._bot_provider = _SpyBotProvider()
    agent._notifier = _FakeNotifier()
    return meeting, session, agent


async def _drive_question(agent, question: TranscriptSegment, decide: str | None = None):
    """Run the agent, ingest one directed question, optionally decide the resulting
    approval request from a SECOND session (as the endpoint in another worker would),
    and return (events, request_id) after the session wraps."""
    from app.tests.conftest import TestSession

    events: list[dict[str, Any]] = []

    async def _consume() -> None:
        async for e in agent.run():
            events.append(e)

    task = asyncio.create_task(_consume())
    for _ in range(200):
        if agent._session.status in ("active", "done", "error") or task.done():
            break
        await asyncio.sleep(0.05)
    await agent.ingest_transcript_segment(question)

    request_id = None
    for _ in range(200):
        if any(e["type"] in ("approval_request", "delegate_reply", "delegate_follow_up") for e in events):
            break
        if task.done():
            break
        await asyncio.sleep(0.05)
    ev = next((e for e in events if e["type"] == "approval_request"), None)
    if ev:
        request_id = ev["request_id"]

    if decide and request_id:
        async with TestSession() as other:
            row = await other.get(ApprovalRequest, request_id)
            row.status = decide
            row.decided_at = datetime.now(UTC)
            await other.commit()

    # Wait until the question was fully handled (spoken reply or follow-up filed)
    for _ in range(300):
        if task.done():
            break
        if any(e["type"] in ("delegate_reply", "delegate_follow_up") and e.get("kind") != "never_commit"
               for e in events):
            break
        await asyncio.sleep(0.05)
    agent.stop()
    await asyncio.wait_for(task, timeout=30)
    return events, request_id


async def _audit_rows(db, action: str, resource_id: str) -> list[AuditLog]:
    return list((await db.execute(
        select(AuditLog).where(AuditLog.action == action, AuditLog.resource_id == resource_id)
        .order_by(AuditLog.created_at)
    )).scalars().all())


# ── Feature flag ───────────────────────────────────────────────────────────


def test_interactive_flag_defaults_off():
    assert get_settings().delegate_interactive_enabled is False


@pytest.mark.asyncio
async def test_interactive_start_403_when_disabled(client, auth_token, db_session, test_workspace):
    meeting = Meeting(workspace_id=test_workspace.id, title="Flag off", mode=MeetingMode.PROXY,
                      proxy_consent_given=True, meeting_url="https://zoom.us/j/1")
    db_session.add(meeting)
    await db_session.flush()
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/meetings/{meeting.id}/delegate/start",
        json={"stage": "interactive"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 403
    assert "pending legal review" in r.json()["detail"]
    rows = (await db_session.execute(
        select(DelegateSession).where(DelegateSession.meeting_id == meeting.id)
    )).scalars().all()
    assert rows == []


# ── Stage C behavior ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_directed_question_creates_approval_request(db_session, iws, monkeypatch):
    _patch_interactive(monkeypatch, timeout_s=1)
    _, session, agent = await _make_agent(db_session, iws)

    events, request_id = await _drive_question(
        agent, _seg("David Lee", "What's the rollout status, Alex?", ts=2000)
    )

    assert request_id is not None
    ev = next(e for e in events if e["type"] == "approval_request")
    assert ev["question"] == "What's the rollout status, Alex?"
    assert ev["proposed_answer"] == _PROPOSED_ANSWER
    request = await db_session.get(ApprovalRequest, request_id)
    assert request.delegate_session_id == session.id
    assert json.loads(request.sources_json) == [
        {"chunk_id": "chunk-1", "source_type": "transcript", "meeting_id": "m-prev"}
    ]
    assert agent._notifier.calls and len(agent._notifier.calls) == 1
    assert "/approvals" in agent._notifier.calls[0]["click_url"]
    assert len(await _audit_rows(db_session, "delegate.approval_requested", request_id)) == 1


@pytest.mark.asyncio
async def test_approved_answer_is_spoken_and_audited(db_session, iws, monkeypatch):
    _patch_interactive(monkeypatch, timeout_s=6)
    _, session, agent = await _make_agent(db_session, iws)

    events, request_id = await _drive_question(
        agent, _seg("David Lee", "What's the rollout status, Alex?"), decide="approved"
    )

    reply = next(e for e in events if e["type"] == "delegate_reply" and e.get("kind") == "approved_answer")
    assert reply["text"] == _PROPOSED_ANSWER and reply["request_id"] == request_id
    utterances = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "delegate.utterance", AuditLog.resource_id == session.id)
    )).scalars().all()
    kinds = {json.loads(u.detail)["kind"]: json.loads(u.detail)["text"] for u in utterances}
    assert kinds.get("approved_answer") == _PROPOSED_ANSWER
    assert _PROPOSED_ANSWER in agent._tts.spoken
    request = await db_session.get(ApprovalRequest, request_id)
    assert request.status == "approved"
    assert not [e for e in events if e["type"] == "delegate_follow_up"]  # answered, not deferred
    assert session.follow_ups_json is None


@pytest.mark.asyncio
async def test_declined_answer_stays_silent(db_session, iws, monkeypatch):
    _patch_interactive(monkeypatch, timeout_s=6)
    _, session, agent = await _make_agent(db_session, iws)

    events, request_id = await _drive_question(
        agent, _seg("David Lee", "What's the rollout status, Alex?"), decide="declined"
    )

    assert not [e for e in events if e.get("kind") == "approved_answer"]
    utterances = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "delegate.utterance", AuditLog.resource_id == session.id)
    )).scalars().all()
    assert [json.loads(u.detail)["kind"] for u in utterances] == ["disclosure"]  # silence
    follow_ups = json.loads(session.follow_ups_json)
    assert follow_ups[0]["asker"] == "David Lee"
    request = await db_session.get(ApprovalRequest, request_id)
    assert request.status == "declined"


@pytest.mark.asyncio
async def test_approval_timeout_defaults_to_silence(db_session, iws, monkeypatch):
    _patch_interactive(monkeypatch, timeout_s=1)
    _, session, agent = await _make_agent(db_session, iws)

    events, request_id = await _drive_question(
        agent, _seg("David Lee", "What's the rollout status, Alex?")
    )

    # The engine flips to timeout via a Core UPDATE — re-read past the identity map
    request = (await db_session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert request.status == "timeout"
    assert len(await _audit_rows(db_session, "delegate.approval_timeout", request_id)) == 1
    utterances = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "delegate.utterance", AuditLog.resource_id == session.id)
    )).scalars().all()
    assert [json.loads(u.detail)["kind"] for u in utterances] == ["disclosure"]  # silence
    assert json.loads(session.follow_ups_json)[0]["text"] == "What's the rollout status, Alex?"


@pytest.mark.asyncio
async def test_restricted_topic_never_creates_approval_request(db_session, iws, monkeypatch):
    rag = _patch_interactive(monkeypatch, timeout_s=1)
    _, session, agent = await _make_agent(db_session, iws)

    events, request_id = await _drive_question(
        agent, _seg("Priya Patel", "Alex, can you approve the extra budget?")
    )

    assert request_id is None
    rows = (await db_session.execute(
        select(ApprovalRequest).where(ApprovalRequest.delegate_session_id == session.id)
    )).scalars().all()
    assert rows == []
    assert rag.await_count == 0  # the KB is never consulted for restricted topics
    utterances = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "delegate.utterance", AuditLog.resource_id == session.id)
    )).scalars().all()
    kinds = [json.loads(u.detail)["kind"] for u in utterances]
    assert kinds == ["disclosure", "never_commit"]
    assert json.loads(session.follow_ups_json)[0]["asker"] == "Priya Patel"


# ── Decision endpoint ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decision_endpoint_shapes_and_409_on_double_decide(
    client, auth_token, db_session, test_user, iws,
):
    """List + decide shapes, and 409 once decided. The endpoint commits, so the
    committed user is deleted at the end (iws cleans the workspace)."""
    uid = test_user.id
    meeting = Meeting(workspace_id=iws.id, title="Approvals mtg", mode=MeetingMode.PROXY,
                      proxy_consent_given=True)
    db_session.add(meeting)
    await db_session.flush()
    member_ws = iws.id
    from app.models.user import WorkspaceMember, WorkspaceRole
    db_session.add(WorkspaceMember(workspace_id=member_ws, user_id=uid, role=WorkspaceRole.OWNER))
    session = DelegateSession(meeting_id=meeting.id, workspace_id=iws.id, stage="interactive",
                              consent_recorded_at=datetime.now(UTC))
    db_session.add(session)
    await db_session.flush()
    request = ApprovalRequest(
        delegate_session_id=session.id, meeting_id=meeting.id, workspace_id=iws.id,
        question_text="What's the rollout status?", proposed_answer=_PROPOSED_ANSWER,
        sources_json=json.dumps([{"chunk_id": "chunk-1", "source_type": "transcript", "meeting_id": None}]),
    )
    db_session.add(request)
    await db_session.flush()
    headers = {"Authorization": f"Bearer {auth_token}"}
    base = f"/api/workspaces/{member_ws}/approvals"

    try:
        r = await client.get(base, headers=headers)  # default status=pending
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["id"] == request.id
        assert items[0]["meeting_title"] == "Approvals mtg"
        assert items[0]["question_text"] == "What's the rollout status?"
        assert items[0]["proposed_answer"] == _PROPOSED_ANSWER
        assert items[0]["sources"][0]["chunk_id"] == "chunk-1"
        assert items[0]["status"] == "pending"

        r = await client.post(f"{base}/{request.id}/decision", json={"decision": "approved"}, headers=headers)
        assert r.status_code == 200, r.text
        decided = r.json()
        assert decided["status"] == "approved"
        assert decided["decided_by_id"] == uid
        assert decided["decided_at"] is not None

        r = await client.post(f"{base}/{request.id}/decision", json={"decision": "declined"}, headers=headers)
        assert r.status_code == 409

        r = await client.post(f"{base}/{uuid.uuid4()}/decision", json={"decision": "approved"}, headers=headers)
        assert r.status_code == 404

        r = await client.post(f"{base}/{request.id}/decision", json={"decision": "maybe"}, headers=headers)
        assert r.status_code == 422

        r = await client.get(f"{base}?status=approved", headers=headers)
        assert [i["id"] for i in r.json()] == [request.id]
        assert (await _audit_rows(db_session, "delegate.approval_decided", request.id))[0].detail == "approved"
    finally:
        await db_session.rollback()
        await db_session.execute(delete(User).where(User.id == uid))
        await db_session.commit()


# ── Notifier ───────────────────────────────────────────────────────────────


def test_get_notifier_defaults_to_log():
    assert isinstance(notify.get_notifier(), notify.LogNotifier)


@pytest.mark.asyncio
async def test_ntfy_notifier_contract_and_never_raises(monkeypatch):
    monkeypatch.setattr(get_settings(), "approval_notify_provider", "ntfy")
    monkeypatch.setattr(get_settings(), "ntfy_base_url", "https://ntfy.test")
    monkeypatch.setattr(get_settings(), "ntfy_topic", "ammeet-approvals")
    assert isinstance(notify.get_notifier(), notify.NtfyNotifier)

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    real_client = httpx.AsyncClient
    notify.httpx.AsyncClient = lambda *a, **k: real_client(transport=httpx.MockTransport(handler))
    try:
        await notify.NtfyNotifier().send("Approval needed", "Q: status?", "https://app/approvals")
        assert captured["url"] == "https://ntfy.test/ammeet-approvals"
        assert captured["headers"]["Title"] == "Approval needed"
        assert captured["headers"]["Click"] == "https://app/approvals"
        assert captured["body"] == b"Q: status?"

        def failing(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        notify.httpx.AsyncClient = lambda *a, **k: real_client(transport=httpx.MockTransport(failing))
        await notify.NtfyNotifier().send("t", "b", "u")  # must not raise
    finally:
        notify.httpx.AsyncClient = real_client
