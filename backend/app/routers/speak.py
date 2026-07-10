"""Speak Mode — a silent live speaking companion.

Prepare: raw notes → structured, prioritized speaking points.
Present: ingest live transcript → auto-mark points covered + capture participant responses.
Wrap:    finalize → summary (covered / missed / responses / action items / follow-ups).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.models.meeting import ContextSource, Meeting, Report
from app.models.speaking import PointStatus, SpeakingPoint, SpeakingResponse
from app.models.user import User, Workspace, WorkspaceRole
from app.services import speak_coverage
from app.services.billing import check_and_increment_usage

router = APIRouter()


async def _meeting_or_404(db: AsyncSession, workspace_id: str, meeting_id: str) -> Meeting:
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


def _point_out(p: SpeakingPoint) -> dict[str, Any]:
    return {
        "id": p.id, "text": p.text, "stage": p.stage, "priority": p.priority,
        "order_index": p.order_index, "status": p.status, "covered_by_text": p.covered_by_text,
    }


async def _state(db: AsyncSession, meeting_id: str) -> dict[str, Any]:
    pts = (await db.execute(
        select(SpeakingPoint).where(SpeakingPoint.meeting_id == meeting_id).order_by(SpeakingPoint.order_index)
    )).scalars().all()
    resps = (await db.execute(
        select(SpeakingResponse).where(SpeakingResponse.meeting_id == meeting_id).order_by(SpeakingResponse.created_at)
    )).scalars().all()
    covered = sum(1 for p in pts if p.status == PointStatus.COVERED.value)
    missed = sum(1 for p in pts if p.status == PointStatus.MISSED.value)
    must_remaining = sum(
        1 for p in pts if p.status == PointStatus.PENDING.value and p.priority == "must"
    )
    return {
        "points": [_point_out(p) for p in pts],
        "responses": [
            {"id": r.id, "speaker": r.speaker, "text": r.text, "kind": r.kind, "point_id": r.point_id}
            for r in resps
        ],
        "progress": {
            "total": len(pts), "covered": covered, "missed": missed,
            "pending": len(pts) - covered - missed, "must_remaining": must_remaining,
        },
    }


# ── Prepare ────────────────────────────────────────────────────────────────────

class GeneratePointsRequest(BaseModel):
    text: str | None = None       # raw notes pasted directly
    source_id: str | None = None  # OR a previously-uploaded ContextSource
    replace: bool = True          # clear existing points first


@router.post("/{workspace_id}/meetings/{meeting_id}/speak/points/generate")
async def generate_points(
    workspace_id: str,
    meeting_id: str,
    body: GeneratePointsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    await _meeting_or_404(db, workspace_id, meeting_id)

    raw = (body.text or "").strip()
    if not raw and body.source_id:
        src = (await db.execute(
            select(ContextSource).where(
                ContextSource.id == body.source_id, ContextSource.meeting_id == meeting_id
            )
        )).scalar_one_or_none()
        raw = (src.raw_text or "").strip() if src else ""
    if not raw:
        raise HTTPException(status_code=400, detail="Provide `text` or a `source_id` with extracted text.")

    # Free-tier gate: preparing a session's points counts as one Speak session.
    workspace = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one()
    await check_and_increment_usage(db, workspace, "speak_sessions")

    points = await speak_coverage.generate_points(raw)
    if not points:
        raise HTTPException(status_code=422, detail="Could not derive any speaking points from that text.")

    if body.replace:
        existing = (await db.execute(
            select(SpeakingPoint).where(SpeakingPoint.meeting_id == meeting_id)
        )).scalars().all()
        for p in existing:
            await db.delete(p)
        await db.flush()

    for i, p in enumerate(points):
        db.add(SpeakingPoint(
            meeting_id=meeting_id, workspace_id=workspace_id,
            text=p["text"], stage=p["stage"], priority=p["priority"], order_index=i,
        ))
    await db.flush()
    return await _state(db, meeting_id)


@router.get("/{workspace_id}/meetings/{meeting_id}/speak/state")
async def get_state(
    workspace_id: str,
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.VIEWER)
    await _meeting_or_404(db, workspace_id, meeting_id)
    return await _state(db, meeting_id)


class UpdatePointRequest(BaseModel):
    text: str | None = None
    stage: str | None = None
    priority: str | None = None
    status: str | None = None  # manual override: pending | covered | missed


@router.put("/{workspace_id}/meetings/{meeting_id}/speak/points/{point_id}")
async def update_point(
    workspace_id: str,
    meeting_id: str,
    point_id: str,
    body: UpdatePointRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    point = (await db.execute(
        select(SpeakingPoint).where(SpeakingPoint.id == point_id, SpeakingPoint.meeting_id == meeting_id)
    )).scalar_one_or_none()
    if not point:
        raise HTTPException(status_code=404, detail="Point not found")
    if body.text is not None:
        point.text = body.text.strip()[:500]
    if body.stage is not None:
        point.stage = body.stage.strip()[:80] or "Main"
    if body.priority in ("must", "should", "nice"):
        point.priority = body.priority
    if body.status in ("pending", "covered", "missed"):
        point.status = body.status
        point.covered_at = datetime.now(UTC) if body.status == "covered" else None
    await db.flush()
    return _point_out(point)


# ── Present (live) ─────────────────────────────────────────────────────────────

class Segment(BaseModel):
    speaker: str
    text: str


class IngestRequest(BaseModel):
    segments: list[Segment]


@router.post("/{workspace_id}/meetings/{meeting_id}/speak/ingest")
async def ingest(
    workspace_id: str,
    meeting_id: str,
    body: IngestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    await _meeting_or_404(db, workspace_id, meeting_id)

    owner_name = user.full_name or user.email
    # Normalize the speaker's own mic label so the matcher can tell "you" from participants.
    lines = []
    for s in body.segments:
        who = owner_name if s.speaker.lower().startswith("you") else s.speaker
        if s.text.strip():
            lines.append(f"{who}: {s.text.strip()}")
    transcript_text = "\n".join(lines)

    pending = (await db.execute(
        select(SpeakingPoint).where(
            SpeakingPoint.meeting_id == meeting_id,
            SpeakingPoint.status == PointStatus.PENDING.value,
        )
    )).scalars().all()

    result = await speak_coverage.match_coverage(
        [{"id": p.id, "text": p.text} for p in pending], transcript_text, owner_name
    )

    by_id = {p.id: p for p in pending}
    newly_covered: list[str] = []
    for c in result["covered"]:
        p = by_id.get(c["id"])
        if p and p.status == PointStatus.PENDING.value:
            p.status = PointStatus.COVERED.value
            p.covered_at = datetime.now(UTC)
            p.covered_by_text = c.get("evidence") or None
            newly_covered.append(p.id)
    for r in result["responses"]:
        db.add(SpeakingResponse(
            meeting_id=meeting_id, workspace_id=workspace_id, point_id=r["point_id"],
            speaker=r["speaker"], text=r["text"], kind=r["kind"],
        ))
    await db.flush()

    state = await _state(db, meeting_id)
    state["newly_covered"] = newly_covered
    return state


# ── Wrap ───────────────────────────────────────────────────────────────────────

@router.post("/{workspace_id}/meetings/{meeting_id}/speak/finalize")
async def finalize(
    workspace_id: str,
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await require_workspace_role(workspace_id, user, db, WorkspaceRole.MEMBER)
    await _meeting_or_404(db, workspace_id, meeting_id)

    pts = (await db.execute(
        select(SpeakingPoint).where(SpeakingPoint.meeting_id == meeting_id).order_by(SpeakingPoint.order_index)
    )).scalars().all()
    # Anything still pending at the end was missed.
    for p in pts:
        if p.status == PointStatus.PENDING.value:
            p.status = PointStatus.MISSED.value
    resps = (await db.execute(
        select(SpeakingResponse).where(SpeakingResponse.meeting_id == meeting_id)
    )).scalars().all()

    covered = [p.text for p in pts if p.status == PointStatus.COVERED.value]
    missed = [p.text for p in pts if p.status == PointStatus.MISSED.value]
    summary = await speak_coverage.summarize_session(
        covered, missed, [{"kind": r.kind, "text": r.text} for r in resps]
    )

    report = Report(
        meeting_id=meeting_id, workspace_id=workspace_id,
        summary=summary.get("summary") or "",
        full_json=json.dumps({
            "mode": "speak", "covered": covered, "missed": missed,
            "responses": [{"speaker": r.speaker, "text": r.text, "kind": r.kind} for r in resps],
            **summary,
        }),
    )
    db.add(report)
    await db.flush()
    return {
        "summary": summary.get("summary") or "",
        "covered": covered, "missed": missed,
        "action_items": summary.get("action_items") or [],
        "follow_ups": summary.get("follow_ups") or [],
        "responses": [{"speaker": r.speaker, "text": r.text, "kind": r.kind} for r in resps],
        "report_id": report.id,
    }
