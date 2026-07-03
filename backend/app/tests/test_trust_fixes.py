from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_escalation_fails_closed_when_classifier_errors():
    """If the safety classifier is unavailable, a non-obvious topic must escalate to a
    human rather than be silently allowed through."""
    from app.services.escalation import classify_escalation

    # Benign text (no regex hit) so it reaches the LLM path; force the LLM to fail.
    with patch("app.services.escalation.get_llm", side_effect=RuntimeError("llm down")):
        result = await classify_escalation("Let's talk through the project roadmap.")
    assert result["requires_escalation"] is True


@pytest.mark.asyncio
async def test_transcript_webhook_rejects_without_token(client):
    r = await client.post("/api/webhooks/recall/any-meeting", json={"event": "ping", "data": {}})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_transcript_webhook_accepts_valid_token(client):
    from app.core.security import webhook_secret

    r = await client.post(
        f"/api/webhooks/recall/any-meeting?token={webhook_secret()}",
        json={"event": "ping", "data": {}},
    )
    assert r.status_code != 401  # authenticated (event is a no-op, but not rejected)


@pytest.mark.asyncio
async def test_transcript_webhook_rejects_forged_token(client):
    r = await client.post(
        "/api/webhooks/recall/any-meeting?token=forged-token",
        json={"event": "ping", "data": {}},
    )
    assert r.status_code == 401
