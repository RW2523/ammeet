from __future__ import annotations

import asyncio
from typing import Any


class MockJiraProvider:
    """Returns realistic Jira fixture data. Replace with real OAuth impl later."""

    _TICKETS: list[dict[str, Any]] = [
        {
            "key": "PROJ-101",
            "summary": "API authentication implementation",
            "status": "In Progress",
            "assignee": "John Smith",
            "priority": "High",
            "sprint": "Sprint 12",
            "deadline": "2026-06-10",
            "comments": ["Auth flow partially complete", "Blocked on token refresh logic"],
            "blockers": ["Token refresh logic not yet implemented"],
        },
        {
            "key": "PROJ-102",
            "summary": "Dashboard UI final design approval",
            "status": "Review",
            "assignee": "Sarah Chen",
            "priority": "High",
            "sprint": "Sprint 12",
            "deadline": "2026-06-12",
            "comments": ["Client feedback round 2 done", "Awaiting final sign-off"],
            "blockers": ["Client approval pending"],
        },
        {
            "key": "PROJ-103",
            "summary": "Frontend integration testing",
            "status": "To Do",
            "assignee": "Mike Torres",
            "priority": "Medium",
            "sprint": "Sprint 13",
            "deadline": "2026-06-17",
            "comments": ["Blocked on API readiness"],
            "blockers": ["Depends on PROJ-101"],
        },
        {
            "key": "PROJ-104",
            "summary": "Deployment pipeline stabilization",
            "status": "In Progress",
            "assignee": "John Smith",
            "priority": "Medium",
            "sprint": "Sprint 12",
            "deadline": "2026-06-13",
            "comments": ["Pipeline flaky on staging env"],
            "blockers": [],
        },
    ]

    async def get_tickets(self, workspace_id: str) -> list[dict[str, Any]]:
        await asyncio.sleep(0.05)
        return self._TICKETS

    async def get_ticket(self, ticket_key: str) -> dict[str, Any] | None:
        await asyncio.sleep(0.05)
        return next((t for t in self._TICKETS if t["key"] == ticket_key), None)

    async def update_ticket(self, ticket_key: str, updates: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {"key": ticket_key, "updated": True, **updates}


class MockCalendarProvider:
    """Returns realistic Google Calendar fixture data."""

    async def get_upcoming_events(self, workspace_id: str) -> list[dict[str, Any]]:
        await asyncio.sleep(0.05)
        return [
            {
                "id": "cal_001",
                "title": "Client Dashboard Review",
                "start": "2026-06-07T10:00:00-04:00",
                "end": "2026-06-07T11:00:00-04:00",
                "attendees": [
                    {"name": "Richard Watson", "email": "richard@company.com"},
                    {"name": "David Lee", "email": "david@client.com"},
                    {"name": "Sarah Chen", "email": "sarah@company.com"},
                    {"name": "John Smith", "email": "john@company.com"},
                ],
                "description": "Review dashboard design changes and API delivery status.",
                "recurring": True,
            }
        ]


class MockSlackProvider:
    """Stub Slack provider — logs messages without sending."""

    async def send_message(self, channel: str, text: str) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {"ok": True, "channel": channel, "stub": True, "message": "Stub: message not sent to real Slack"}

    async def send_dm(self, user_email: str, text: str) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {"ok": True, "user": user_email, "stub": True}


def get_jira() -> MockJiraProvider:
    return MockJiraProvider()


def get_calendar() -> MockCalendarProvider:
    return MockCalendarProvider()


def get_slack() -> MockSlackProvider:
    return MockSlackProvider()
