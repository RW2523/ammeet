"""Public, unauthenticated read-only endpoints.

Only data the workspace has explicitly chosen to share (via an opaque, revocable
share token) is exposed here. No token → 404. Nothing here requires auth, so it must
never return anything that wasn't deliberately shared.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.meeting import Meeting, Report

router = APIRouter()


@router.get("/reports/{token}")
async def public_report(token: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return a read-only recap for a shared report. 404 unless the token matches."""
    if not token or len(token) < 16:
        raise HTTPException(status_code=404, detail="Not found")
    report = (await db.execute(
        select(Report).where(Report.share_token == token)
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="This recap link is invalid or was revoked.")

    meeting = (await db.execute(
        select(Meeting).where(Meeting.id == report.meeting_id)
    )).scalar_one_or_none()

    try:
        full = json.loads(report.full_json) if report.full_json else {}
    except (ValueError, TypeError):
        full = {}

    # Expose only presentation-safe fields — never workspace/meeting internals.
    return {
        "title": meeting.title if meeting else "Meeting recap",
        "summary": report.summary or full.get("summary") or "",
        "mode": full.get("mode"),
        "covered": full.get("covered") or [],
        "missed": full.get("missed") or [],
        "action_items": full.get("action_items") or [],
        "follow_ups": full.get("follow_ups") or [],
        "responses": full.get("responses") or [],
        "shared_at": report.shared_at.isoformat() if report.shared_at else None,
    }
