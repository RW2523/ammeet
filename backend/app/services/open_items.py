"""Wrap-time writer — persist extracted open items (commitments / actions /
decisions / open questions) as first-class rows so later meetings can query them.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meeting import ActionItem, Decision, Question, QuestionPriority, QuestionStatus


async def persist_open_items(
    db: AsyncSession,
    meeting_id: str,
    workspace_id: str,
    extracted: dict[str, list[dict[str, Any]]],
    *,
    source_context: str,
    question_source_context: str | None = None,
) -> None:
    """Write one extraction pass for a meeting. Idempotent: rows this source wrote
    before are replaced, not duplicated (regenerating a report re-extracts)."""
    q_source = question_source_context or source_context
    await db.execute(delete(ActionItem).where(
        ActionItem.meeting_id == meeting_id, ActionItem.source_context == source_context
    ))
    await db.execute(delete(Decision).where(
        Decision.meeting_id == meeting_id, Decision.source_context == source_context
    ))
    await db.execute(delete(Question).where(
        Question.meeting_id == meeting_id, Question.source_context == q_source
    ))

    for kind, bucket in (("commitment", "commitments"), ("action", "actions")):
        for item in extracted.get(bucket) or []:
            db.add(ActionItem(
                meeting_id=meeting_id, workspace_id=workspace_id, kind=kind,
                title=item["title"], owner=item.get("owner"), deadline=item.get("deadline"),
                source_context=source_context,
            ))
    for d in extracted.get("decisions") or []:
        db.add(Decision(
            meeting_id=meeting_id, workspace_id=workspace_id,
            text=d["text"], made_by=d.get("made_by"), source_context=source_context,
        ))
    for q in extracted.get("open_questions") or []:
        db.add(Question(
            meeting_id=meeting_id, workspace_id=workspace_id, text=q["text"],
            priority=QuestionPriority.MUST_ASK, status=QuestionStatus.PENDING,
            source_context=q_source,
        ))
    await db.flush()
