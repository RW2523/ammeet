from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_escalation_classifier_restricted_topics():
    """Escalation classifier must flag budget/legal/HR topics."""
    from app.services.escalation import is_restricted_topic, classify_escalation

    assert is_restricted_topic("Can you approve the budget for this?") is True
    assert is_restricted_topic("We need to sign the contract today") is True
    assert is_restricted_topic("Should we hire this candidate?") is True
    assert is_restricted_topic("What is the API status?") is False
    assert is_restricted_topic("When will this be delivered?") is False


@pytest.mark.asyncio
async def test_escalation_classifier_llm_fallback():
    """LLM fallback returns valid structure."""
    from app.services.escalation import classify_escalation

    mock_result = {"requires_escalation": False, "reason": None, "confidence": 0.8}
    with patch("app.services.escalation.get_llm") as mock_llm:
        llm_instance = AsyncMock()
        llm_instance.complete_json = AsyncMock(return_value=mock_result)
        mock_llm.return_value = llm_instance

        result = await classify_escalation("What is the current API status?")
        assert "requires_escalation" in result


@pytest.mark.asyncio
async def test_question_generator():
    """Question generator returns categorized questions."""
    from app.services.question_generator import generate_questions

    mock_questions = {
        "questions": [
            {
                "text": "Is the API authentication issue resolved?",
                "category": "status",
                "priority": "must_ask",
                "proxy_allowed": True,
                "human_only": False,
                "confidence": 0.9,
                "source_context": "PROJ-101 is in progress",
            },
            {
                "text": "Can we approve the final budget?",
                "category": "decision",
                "priority": "must_ask",
                "proxy_allowed": False,
                "human_only": True,
                "confidence": 0.85,
                "source_context": "Budget discussion pending",
            },
        ]
    }

    with patch("app.services.question_generator.get_llm") as mock_llm:
        llm_instance = AsyncMock()
        llm_instance.complete_json = AsyncMock(return_value=mock_questions)
        mock_llm.return_value = llm_instance

        context = {"meeting_purpose": "Sprint review", "previous_summary": "API work in progress"}
        knowledge = ["API auth was blocked on token refresh logic"]
        jira = [{"key": "PROJ-101", "summary": "API auth", "status": "In Progress", "assignee": "John", "blockers": ["Token refresh"]}]
        people = [{"name": "John", "role": "Dev", "current_work": "API", "follow_up": "Status?"}]

        questions = await generate_questions(context, knowledge, jira, people)
        assert len(questions) == 2
        # Budget question should be human_only
        budget_q = next(q for q in questions if "budget" in q["text"].lower())
        assert budget_q["human_only"] is True
        assert budget_q["proxy_allowed"] is False


@pytest.mark.asyncio
async def test_retention_policy_defaults(client, auth_token, test_workspace):
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/retention-policy",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "audio_retention_days" in data or data.get("policy") == "default"


@pytest.mark.asyncio
async def test_full_meeting_flow(client, auth_token, test_workspace):
    """Integration: create meeting -> add question -> approve for proxy."""
    ws_id = test_workspace.id
    headers = {"Authorization": f"Bearer {auth_token}"}

    # Create meeting
    r = await client.post(
        f"/api/workspaces/{ws_id}/meetings",
        headers=headers,
        json={"title": "Sprint Review", "purpose": "Review API progress", "mode": "proxy"},
    )
    assert r.status_code == 201
    meeting_id = r.json()["id"]

    # Add question manually
    r = await client.post(
        f"/api/workspaces/{ws_id}/meetings/{meeting_id}/questions",
        headers=headers,
        json={
            "text": "Is the API authentication issue resolved?",
            "category": "status",
            "priority": "must_ask",
        },
    )
    assert r.status_code == 201
    q_id = r.json()["id"]

    # Mark question as proxy-allowed
    r = await client.patch(
        f"/api/workspaces/{ws_id}/meetings/{meeting_id}/questions/{q_id}",
        headers=headers,
        json={"proxy_allowed": True},
    )
    assert r.status_code == 200
    assert r.json()["proxy_allowed"] is True

    # List questions
    r = await client.get(
        f"/api/workspaces/{ws_id}/meetings/{meeting_id}/questions",
        headers=headers,
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
