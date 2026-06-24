from __future__ import annotations

import pytest

from app.models.meeting import Meeting, MeetingMode
from app.services import meeting_assistant as ma


class _FakeTTS:
    async def synthesize(self, text):
        return None  # no audio in tests


class _FakeLLM:
    """Replies to a normal question; the summary returns a fixed structure."""

    async def complete_json(self, system, user):
        if "Summarize" in system:
            return {
                "summary": "Team is on track; ship Friday.",
                "decisions": [{"text": "Ship Friday", "made_by": "Bob"}],
                "action_items": [{"title": "Ship release", "owner": "Bob", "deadline": "Friday"}],
                "risks": [],
                "open_questions": [],
            }
        # decide() — respond to a direct question
        return {"respond": True, "reply": "The project is on track and shipping Friday.", "reason": "addressed"}

    async def complete(self, system, user, temperature: float = 0.3):
        return "ok"


async def _make_agent(db, workspace_id, mode):
    meeting = Meeting(workspace_id=workspace_id, title="Assistant test", mode=MeetingMode.PROXY,
                      proxy_consent_given=True)
    db.add(meeting)
    await db.flush()
    agent = ma.MeetingAssistantAgent(
        db=db, meeting=meeting, owner_name="Owner",
        mode=mode, assistant_name="AmMeeting", simulate=True,
    )
    agent._llm = _FakeLLM()
    agent._tts = _FakeTTS()
    return agent


@pytest.mark.asyncio
async def test_recorder_mode_never_speaks_but_summarizes(db_session, test_workspace, monkeypatch):
    monkeypatch.setattr(ma, "_SIM_CONVERSATION", [("Alice", "Project is on track."), ("Bob", "We ship Friday.")])
    agent = await _make_agent(db_session, test_workspace.id, ma.AssistantMode.RECORDER)

    events = [e async for e in agent.run()]
    types = [e["type"] for e in events]

    assert "disclosure" in types
    assert "summary" in types
    assert "session_complete" in types
    # Recorder must stay silent — no replies and no audio
    assert "assistant_reply" not in types
    assert "tts_audio" not in types
    summary = next(e for e in events if e["type"] == "summary")
    assert "track" in summary["summary"].lower()
    assert len(summary["action_items"]) == 1


@pytest.mark.asyncio
async def test_assistant_mode_replies_and_escalates(db_session, test_workspace, monkeypatch):
    monkeypatch.setattr(ma, "_SIM_CONVERSATION", [
        ("Dave", "AmMeeting, what's the project status?"),       # answerable -> reply
        ("Dave", "Also, can you approve the extra budget now?"),  # restricted -> escalate
    ])
    agent = await _make_agent(db_session, test_workspace.id, ma.AssistantMode.ASSISTANT)

    events = [e async for e in agent.run()]
    types = [e["type"] for e in events]

    assert "assistant_reply" in types         # it answered the status question
    assert "escalation" in types              # it refused / escalated the budget approval
    reply = next(e for e in events if e["type"] == "assistant_reply")
    assert "Friday" in reply["text"]
    esc = next(e for e in events if e["type"] == "escalation")
    assert "approve" in esc["text"].lower()


def test_assistant_modes_enum():
    assert ma.AssistantMode.ASSISTANT.value == "assistant"
    assert ma.AssistantMode.RECORDER.value == "recorder"
