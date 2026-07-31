"""Live nudges — check a fresh transcript chunk against the workspace's memory:
open commitments/actions/questions from past meetings and recorded decisions.
Pure LLM helper (takes/returns plain data) so the router owns the DB and this
stays trivially testable by mocking get_llm().
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services.llm import get_llm

_logger = get_logger(__name__)

_NUDGE_SYSTEM = """You are a silent meeting memory. You are given OPEN ITEMS from past
meetings (commitments people promised, tasks assigned, unanswered questions — each with an
id) plus recorded DECISIONS (each with an id), and a recent chunk of a live transcript.

Emit a nudge only when the live discussion genuinely touches the workspace memory:
1. "promise" — the discussion touches something someone promised earlier (remind them).
2. "unanswered" — an open question from a past meeting is relevant or being asked again.
3. "conflict" — what is being said contradicts a recorded decision.

Be conservative: no nudge for a vague topical overlap. `item_id` is the id of the matched
open item or decision (null only if none applies). `text` is a short reminder the speaker
can act on; `evidence` quotes the transcript line that triggered it.

Return JSON: {"nudges": [{"kind": "promise|unanswered|conflict", "item_id": str|null,
"text": str, "evidence": str}]}"""

_VALID_NUDGE_KIND = {"promise", "unanswered", "conflict"}


async def match_nudges(
    open_items: list[dict[str, Any]], recent_decisions: list[dict[str, Any]], transcript_text: str
) -> list[dict[str, Any]]:
    """Match a live transcript chunk against open items + decisions. Never raises —
    on any failure returns no nudges."""
    if (not open_items and not recent_decisions) or not (transcript_text or "").strip():
        return []

    valid_ids = {i["id"] for i in open_items} | {d["id"] for d in recent_decisions}
    items_block = "\n".join(
        f'- id={i["id"]} [{i.get("kind") or "action"}] {i["text"]}'
        + (f' (owner: {i["owner"]})' if i.get("owner") else "")
        for i in open_items
    ) or "(none)"
    decisions_block = "\n".join(
        f'- id={d["id"]}: {d["text"]}' + (f' (by {d["made_by"]})' if d.get("made_by") else "")
        for d in recent_decisions
    ) or "(none)"
    user = (
        f"OPEN ITEMS FROM PAST MEETINGS:\n{items_block}\n\n"
        f"RECORDED DECISIONS:\n{decisions_block}\n\n"
        f"RECENT TRANSCRIPT:\n{transcript_text[-4000:]}"
    )
    try:
        data = await get_llm().complete_json(system=_NUDGE_SYSTEM, user=user)
    except Exception as exc:
        _logger.warning("Nudge matching failed: %s", exc)
        return []

    nudges: list[dict[str, Any]] = []
    for n in data.get("nudges") or []:
        if not isinstance(n, dict):
            continue
        text = (n.get("text") or "").strip()
        kind = (n.get("kind") or "").lower()
        if not text or kind not in _VALID_NUDGE_KIND:
            continue
        item_id = n.get("item_id")
        if item_id not in valid_ids:
            item_id = None
        nudges.append({
            "kind": kind,
            "item_id": item_id,
            "text": text[:500],
            "evidence": (n.get("evidence") or "").strip()[:500],
        })
    return nudges[:10]
