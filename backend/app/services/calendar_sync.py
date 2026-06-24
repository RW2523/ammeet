"""Calendar auto-discovery → auto-join meetings.

Reads a workspace's connected calendar (Google / Microsoft), finds upcoming events
that carry a video link (Meet/Teams/Zoom), and materialises them as Meeting rows with
``auto_join_enabled=True`` so the existing auto-join scheduler deploys the bot at start
time. Deduplicates on ``calendar_event_id`` so re-syncing is idempotent.

Enabling auto-join is a consent decision, so the caller passes ``enable_auto_join``
explicitly (the UI "Sync & auto-join" action / an opt-in workspace setting).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import get_logger
from app.models.knowledge import Integration
from app.models.meeting import Meeting, MeetingMode, MeetingStatus
from app.models.user import Workspace
from app.services.integrations import get_calendar

_logger = get_logger(__name__)
_settings = get_settings()

_CALENDAR_PROVIDERS = ("google_calendar", "microsoft_teams")


def _parse_start(value: Any) -> datetime | None:
    """Parse a calendar event start into an aware UTC datetime, or None for all-day/bad."""
    if not isinstance(value, str) or "T" not in value:
        return None  # all-day events (date only) carry no join time
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def sync_workspace_calendar(
    db: AsyncSession, workspace_id: str, *, enable_auto_join: bool = True
) -> dict[str, int]:
    """Create auto-join meetings from a workspace's upcoming calendar events.

    Returns {scanned, created, skipped}. Idempotent via calendar_event_id dedup.
    """
    calendar = await get_calendar(db, workspace_id)
    events = await calendar.get_upcoming_events(workspace_id)

    now = datetime.now(UTC)
    # Only materialise events the scheduler can still act on (its grace window),
    # so we don't create permanently un-dispatchable rows.
    horizon = now - timedelta(minutes=_settings.auto_join_grace_minutes)
    created = skipped = 0

    for event in events:
        meet_link = event.get("meet_link")
        cal_id = event.get("id")
        scheduled_at = _parse_start(event.get("start"))
        if not meet_link or not cal_id or not scheduled_at or scheduled_at < horizon:
            skipped += 1
            continue

        exists = await db.execute(
            select(Meeting.id).where(
                Meeting.workspace_id == workspace_id,
                Meeting.calendar_event_id == cal_id,
            )
        )
        if exists.scalar_one_or_none():
            skipped += 1
            continue

        # Insert inside a savepoint so a race with a concurrent sync (the unique
        # index catches the duplicate) is counted as skipped, not fatal.
        try:
            async with db.begin_nested():
                db.add(
                    Meeting(
                        workspace_id=workspace_id,
                        title=event.get("title") or "Calendar meeting",
                        mode=MeetingMode.PROXY,
                        status=MeetingStatus.READY,
                        scheduled_at=scheduled_at,
                        meeting_url=meet_link,
                        calendar_event_id=cal_id,
                        proxy_consent_given=enable_auto_join,
                        auto_join_enabled=enable_auto_join,
                    )
                )
            created += 1
        except IntegrityError:
            skipped += 1

    await db.flush()
    return {"scanned": len(events), "created": created, "skipped": skipped}


async def sync_all_connected_calendars() -> int:
    """Background sweep: sync every workspace that has a calendar integration connected.
    Returns total meetings created. Used by the optional auto-sync loop."""
    total = 0
    async with AsyncSessionLocal() as db:
        # Only workspaces that EXPLICITLY opted into auto-join (not merely connected a
        # calendar) — connecting a calendar is not consent for an AI bot to attend.
        result = await db.execute(
            select(Integration.workspace_id)
            .join(Workspace, Workspace.id == Integration.workspace_id)
            .where(
                Integration.provider.in_(_CALENDAR_PROVIDERS),
                Integration.status == "connected",
                Workspace.calendar_auto_join_enabled == True,  # noqa: E712
            )
            .distinct()
        )
        workspace_ids = [row[0] for row in result.all()]
        for ws_id in workspace_ids:
            try:
                stats = await sync_workspace_calendar(db, ws_id, enable_auto_join=True)
                total += stats["created"]
                if stats["created"]:
                    _logger.info("Calendar sync: workspace %s created %d auto-join meeting(s)", ws_id, stats["created"])
            except Exception as exc:  # one workspace failing must not stop the sweep
                _logger.warning("Calendar sync failed for workspace %s: %s", ws_id, exc)
        await db.commit()
    return total


async def calendar_sync_loop() -> None:
    """Optional background loop (gated by calendar_auto_sync_enabled) that periodically
    pulls connected calendars into auto-join meetings."""
    interval = max(60, _settings.calendar_auto_sync_minutes * 60)
    _logger.info("Calendar auto-sync loop started (every %ss)", interval)
    while True:
        try:
            await sync_all_connected_calendars()
        except asyncio.CancelledError:
            _logger.info("Calendar auto-sync loop stopping")
            raise
        except Exception as exc:
            _logger.warning("Calendar auto-sync sweep failed: %s", exc)
        await asyncio.sleep(interval)
