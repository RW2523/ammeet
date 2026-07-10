"""Speak Mode brain — turn raw notes into speaking points, track live coverage, and
summarize. Pure LLM helpers (take/return plain data) so the router owns the DB and
these stay trivially testable by mocking get_llm().
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services.llm import get_llm

_logger = get_logger(__name__)

_GEN_SYSTEM = """You turn a speaker's raw notes / agenda / outline into a clean, ordered
list of SPEAKING POINTS to cover during a live session (meeting, client presentation,
sermon, interview, or product demo).

Rules:
- Break the content into concise, self-contained points — one idea each, ~4–16 words.
- Group points into stages/sections (use the document's own sections if present, else
  sensible ones like Intro, Main, Q&A, Close).
- Assign a priority: "must" (core, cannot skip), "should" (important), "nice" (optional).
- Preserve the speaker's intended order.

Return JSON: {"points": [{"text": str, "stage": str, "priority": "must|should|nice"}]}"""

_MATCH_SYSTEM = """You track whether a SPEAKER has covered their prepared points during a
live session. You are given the still-PENDING points (each with an id) and a recent chunk
of the live transcript (the speaker and other participants).

Decide:
1. Which pending points the SPEAKER has now SUBSTANTIVELY covered — a paraphrase counts,
   but a passing mention of the topic without actually addressing it does NOT.
2. Any notable statements from OTHER participants (not the speaker) — responses,
   questions, or decisions — and which point each relates to (or null).

Be conservative: only mark a point covered if it was genuinely addressed.

Return JSON: {"covered": [{"id": str, "evidence": str}],
"responses": [{"speaker": str, "text": str, "kind": "response|question|decision", "point_id": str|null}]}"""

_SUMMARY_SYSTEM = """You write a concise post-session summary for a speaker who used a
live speaking companion. Given the points they covered, the points they missed, and
captured participant responses, produce JSON:
{"summary": str, "action_items": [{"title": str, "owner": str|null}], "follow_ups": [str]}"""

_VALID_PRIORITY = {"must", "should", "nice"}
_VALID_KIND = {"response", "question", "decision"}


async def generate_points(raw_text: str) -> list[dict[str, str]]:
    """Convert raw notes into normalized speaking points."""
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return []
    llm = get_llm()
    data = await llm.complete_json(system=_GEN_SYSTEM, user=f"Raw notes:\n\n{raw_text[:8000]}")
    out: list[dict[str, str]] = []
    for p in data.get("points") or []:
        if not isinstance(p, dict):
            continue
        text = (p.get("text") or "").strip()
        if not text:
            continue
        pri = (p.get("priority") or "should").lower()
        if pri not in _VALID_PRIORITY:
            pri = "should"
        out.append({"text": text[:500], "stage": (p.get("stage") or "Main").strip()[:80] or "Main", "priority": pri})
    return out


async def match_coverage(
    pending_points: list[dict[str, str]], transcript_text: str, owner_name: str
) -> dict[str, Any]:
    """Given pending points + recent transcript, return covered point ids + participant
    responses. Never raises — on any failure returns nothing covered."""
    if not pending_points or not (transcript_text or "").strip():
        return {"covered": [], "responses": []}

    valid_ids = {p["id"] for p in pending_points}
    points_block = "\n".join(f'- id={p["id"]}: {p["text"]}' for p in pending_points)
    user = (
        f"The speaker is {owner_name}.\n\n"
        f"PENDING POINTS:\n{points_block}\n\n"
        f"RECENT TRANSCRIPT:\n{transcript_text[-4000:]}"
    )
    try:
        data = await get_llm().complete_json(system=_MATCH_SYSTEM, user=user)
    except Exception as exc:
        _logger.warning("Speak coverage match failed: %s", exc)
        return {"covered": [], "responses": []}

    covered = [
        {"id": c["id"], "evidence": (c.get("evidence") or "")[:500]}
        for c in (data.get("covered") or [])
        if isinstance(c, dict) and c.get("id") in valid_ids
    ]
    responses: list[dict[str, Any]] = []
    for r in data.get("responses") or []:
        if not isinstance(r, dict):
            continue
        t = (r.get("text") or "").strip()
        if not t:
            continue
        pid = r.get("point_id")
        if pid not in valid_ids:
            pid = None
        kind = (r.get("kind") or "response").lower()
        if kind not in _VALID_KIND:
            kind = "response"
        responses.append({"speaker": (r.get("speaker") or "Participant")[:120], "text": t[:1000], "kind": kind, "point_id": pid})
    return {"covered": covered, "responses": responses}


async def summarize_session(
    covered: list[str], missed: list[str], responses: list[dict[str, str]]
) -> dict[str, Any]:
    """Post-session summary. Never raises."""
    user = (
        "COVERED POINTS:\n" + ("\n".join(f"- {c}" for c in covered) or "(none)") + "\n\n"
        "MISSED POINTS:\n" + ("\n".join(f"- {m}" for m in missed) or "(none)") + "\n\n"
        "PARTICIPANT RESPONSES:\n" + ("\n".join(f"- ({r.get('kind')}) {r.get('text')}" for r in responses) or "(none)")
    )
    try:
        data = await get_llm().complete_json(system=_SUMMARY_SYSTEM, user=user)
    except Exception as exc:
        _logger.warning("Speak summary failed: %s", exc)
        return {"summary": "", "action_items": [], "follow_ups": []}
    return {
        "summary": data.get("summary") or "",
        "action_items": data.get("action_items") or [],
        "follow_ups": data.get("follow_ups") or [],
    }
