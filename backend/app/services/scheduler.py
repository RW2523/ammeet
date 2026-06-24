from __future__ import annotations

"""
Auto-join scheduler.

A lightweight in-process background loop that watches for proxy meetings whose
scheduled start time has arrived and automatically deploys the AI proxy bot —
so the user does not have to manually click "join" at meeting time.

A meeting auto-joins when ALL of these hold:
  - mode == proxy
  - proxy_consent_given == True
  - auto_join_enabled == True
  - meeting_url is set (a real Zoom/Meet/Teams link)
  - scheduled_at is within the join window around now
  - it has not already been dispatched (auto_join_dispatched_at is null)
  - no bot is already active for it
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.meeting import Meeting, MeetingMode, MeetingStatus
from app.models.meeting_bot import BotStatus, MeetingBot
from app.models.user import User, WorkspaceMember, WorkspaceRole
from app.services.live_proxy import launch_session

_logger = get_logger(__name__)
_settings = get_settings()

_ACTIVE_BOT_STATES = [BotStatus.CREATED, BotStatus.JOINING, BotStatus.IN_MEETING]


async def _represented_user_name(db, workspace_id: str) -> str:
    """Best-effort: the workspace owner is the person the proxy represents."""
    result = await db.execute(
        select(User.full_name)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == WorkspaceRole.OWNER,
        )
        .limit(1)
    )
    name = result.scalar_one_or_none()
    return name or "the meeting host"


async def scan_and_dispatch() -> int:
    """Run one scan. Returns the number of meetings dispatched. Safe to call directly in tests."""
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=_settings.auto_join_grace_minutes)
    window_end = now + timedelta(minutes=_settings.auto_join_lead_minutes)

    dispatched = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Meeting).where(
                Meeting.mode == MeetingMode.PROXY,
                Meeting.proxy_consent_given == True,  # noqa: E712
                Meeting.auto_join_enabled == True,  # noqa: E712
                Meeting.auto_join_dispatched_at.is_(None),
                Meeting.meeting_url.isnot(None),
                Meeting.scheduled_at.isnot(None),
                Meeting.scheduled_at >= window_start,
                Meeting.scheduled_at <= window_end,
                Meeting.status.notin_([MeetingStatus.COMPLETED, MeetingStatus.CANCELLED]),
            )
        )
        meetings = list(result.scalars().all())

        for meeting in meetings:
            # Skip if a bot is already active for this meeting
            active = await db.execute(
                select(MeetingBot.id).where(
                    MeetingBot.meeting_id == meeting.id,
                    MeetingBot.status.in_(_ACTIVE_BOT_STATES),
                )
            )
            if active.scalar_one_or_none():
                continue

            # Optimistically claim the dispatch to avoid double-join (commit before launch)
            meeting.auto_join_dispatched_at = now
            await db.commit()

            user_name = await _represented_user_name(db, meeting.workspace_id)
            _logger.info("Auto-joining meeting %s (%s) at scheduled time", meeting.id, meeting.title)
            await launch_session(
                meeting_id=meeting.id,
                workspace_id=meeting.workspace_id,
                user_name=user_name,
                meeting_url=meeting.meeting_url,
                simulate=False,
            )
            dispatched += 1

    return dispatched


async def auto_join_loop() -> None:
    """Long-running poll loop. Started from the app lifespan when enabled."""
    poll = max(15, _settings.auto_join_poll_seconds)
    _logger.info("Auto-join scheduler started (poll=%ss)", poll)
    while True:
        try:
            n = await scan_and_dispatch()
            if n:
                _logger.info("Auto-join scheduler dispatched %d meeting(s)", n)
        except asyncio.CancelledError:
            _logger.info("Auto-join scheduler stopping")
            raise
        except Exception as exc:  # never let the loop die on a transient error
            _logger.warning("Auto-join scan failed: %s", exc)
        await asyncio.sleep(poll)
