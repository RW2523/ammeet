from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.meeting import Meeting
from app.services.calendar_sync import sync_workspace_calendar


class _FakeCalendar:
    def __init__(self, events):
        self._events = events

    async def get_upcoming_events(self, workspace_id):
        return self._events


_EVENTS = [
    {  # has a Meet link + future start -> should become an auto-join meeting
        "id": "evt-with-link",
        "title": "Weekly Sync",
        "start": "2027-01-01T10:00:00+00:00",
        "meet_link": "https://meet.google.com/abc-defg-hij",
    },
    {  # no join link -> skipped
        "id": "evt-no-link",
        "title": "Focus time",
        "start": "2027-01-01T12:00:00+00:00",
        "meet_link": None,
    },
    {  # all-day event (date only) -> skipped
        "id": "evt-all-day",
        "title": "Holiday",
        "start": "2027-01-02",
        "meet_link": "https://meet.google.com/xxx",
    },
]


@pytest.mark.asyncio
async def test_sync_creates_auto_join_meeting_and_is_idempotent(db_session, test_workspace):
    with patch(
        "app.services.calendar_sync.get_calendar",
        new=AsyncMock(return_value=_FakeCalendar(_EVENTS)),
    ):
        stats = await sync_workspace_calendar(db_session, test_workspace.id, enable_auto_join=True)
        assert stats == {"scanned": 3, "created": 1, "skipped": 2}

        meetings = (
            await db_session.execute(select(Meeting).where(Meeting.workspace_id == test_workspace.id))
        ).scalars().all()
        assert len(meetings) == 1
        m = meetings[0]
        assert m.calendar_event_id == "evt-with-link"
        assert m.meeting_url == "https://meet.google.com/abc-defg-hij"
        assert m.auto_join_enabled is True
        assert m.proxy_consent_given is True

        # Re-sync: no duplicates created
        stats2 = await sync_workspace_calendar(db_session, test_workspace.id, enable_auto_join=True)
        assert stats2["created"] == 0


@pytest.mark.asyncio
async def test_sync_endpoint_requires_membership(client, db_session, test_workspace):
    # An unauthenticated request is rejected (401), proving the endpoint is guarded.
    r = await client.post(f"/api/workspaces/{test_workspace.id}/calendar/sync")
    assert r.status_code in (401, 403)
