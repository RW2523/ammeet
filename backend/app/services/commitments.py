"""Remember engine — extract the durable memory of a session from its transcript:
commitments the owner made, tasks assigned to others, decisions taken, and questions
left hanging. Pure LLM helpers (take/return plain data) so callers own the DB and
these stay trivially testable by mocking get_llm().
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services.llm import get_llm

_logger = get_logger(__name__)

_EXTRACT_SYSTEM = """You extract the OPEN ITEMS a team should remember after a live session
(meeting, client call, presentation, or demo). You are given the session owner's name and
a transcript excerpt.

Extract:
1. COMMITMENTS — promises made BY the owner themselves ("I'll send the deck by Friday").
2. ACTIONS — tasks assigned to OTHER participants ("Bob will update the Jira board").
3. DECISIONS — concrete decisions taken during the session.
4. OPEN QUESTIONS — questions raised but left unanswered in the transcript.

Rules:
- Only include items actually stated — never invent owners or deadlines.
- Use null when an owner, deadline, or asker was not mentioned.
- Keep titles/texts short and self-contained.

Return JSON: {"commitments": [{"title": str, "owner": str|null, "deadline": str|null}],
"actions": [{"title": str, "owner": str|null, "deadline": str|null}],
"decisions": [{"text": str, "made_by": str|null}],
"open_questions": [{"text": str, "asker": str|null}]}"""


def _empty() -> dict[str, list[dict[str, Any]]]:
    return {"commitments": [], "actions": [], "decisions": [], "open_questions": []}


def _clamp(value: Any, limit: int) -> str | None:
    text = (str(value) if value is not None else "").strip()
    return text[:limit] or None


def normalize_extracted(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Clamp an LLM extraction payload into the canonical open-items shape. Items
    without a title/text are dropped; strings are trimmed to column-safe lengths."""
    out = _empty()
    for bucket in ("commitments", "actions"):
        for item in data.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            title = _clamp(item.get("title"), 500)
            if not title:
                continue
            out[bucket].append({
                "title": title,
                "owner": _clamp(item.get("owner"), 255),
                "deadline": _clamp(item.get("deadline"), 100),
            })
    for d in data.get("decisions") or []:
        if not isinstance(d, dict):
            continue
        text = _clamp(d.get("text"), 1000)
        if text:
            out["decisions"].append({"text": text, "made_by": _clamp(d.get("made_by"), 255)})
    for q in data.get("open_questions") or []:
        if not isinstance(q, dict):
            continue
        text = _clamp(q.get("text"), 1000)
        if text:
            out["open_questions"].append({"text": text, "asker": _clamp(q.get("asker"), 255)})
    return out


async def extract_open_items(transcript_text: str, owner_name: str) -> dict[str, list[dict[str, Any]]]:
    """Extract commitments / actions / decisions / open questions from a session
    transcript. Never raises — on any failure returns empty buckets."""
    transcript_text = (transcript_text or "").strip()
    if not transcript_text:
        return _empty()
    user = (
        f"The session owner is {owner_name}.\n\n"
        f"TRANSCRIPT:\n{transcript_text[-4000:]}"
    )
    try:
        data = await get_llm().complete_json(system=_EXTRACT_SYSTEM, user=user)
    except Exception as exc:
        _logger.warning("Open-item extraction failed: %s", exc)
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    return normalize_extracted(data)
