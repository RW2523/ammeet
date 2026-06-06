from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.services.llm import get_llm

_logger = get_logger(__name__)

_QUESTION_SYSTEM = """You are AmMeeting, an expert meeting preparation assistant.

Generate smart, targeted questions for an upcoming meeting based on:
- Previous meeting transcripts and notes
- Open Jira tickets and project work
- People, roles, and responsibilities
- Pending action items and decisions
- Known blockers and risks

Return a JSON object with this exact structure:
{
  "questions": [
    {
      "text": str,
      "category": "status"|"blocker"|"ownership"|"deadline"|"client"|"decision"|"risk"|"general",
      "priority": "must_ask"|"if_time"|"ask_later",
      "proxy_allowed": bool,
      "human_only": bool,
      "confidence": float,
      "source_context": str
    }
  ]
}

Rules for proxy_allowed:
- true: factual status, progress updates, clarifying details
- false (human_only): budget, legal, contractual commitments, hiring/firing, sensitive approvals

Generate 8-15 questions. Prioritize must_ask questions about known blockers and open action items.
Order: must_ask first, then if_time, then ask_later."""


async def generate_questions(
    context: dict[str, Any],
    knowledge_chunks: list[str],
    jira_tickets: list[dict],
    people: list[dict],
) -> list[dict[str, Any]]:
    """Generate meeting questions using LLM + context."""
    llm = get_llm()

    context_text = _build_context_text(context, knowledge_chunks, jira_tickets, people)

    try:
        result = await llm.complete_json(
            system=_QUESTION_SYSTEM,
            user=f"Generate meeting questions based on this context:\n\n{context_text}",
        )
        return result.get("questions", [])
    except Exception as exc:
        _logger.error("Question generation failed: %s", exc)
        return []


def _build_context_text(
    context: dict[str, Any],
    knowledge_chunks: list[str],
    jira_tickets: list[dict],
    people: list[dict],
) -> str:
    parts: list[str] = []

    if context.get("meeting_purpose"):
        parts.append(f"MEETING PURPOSE:\n{context['meeting_purpose']}")

    if people:
        people_text = "\n".join(
            f"- {p.get('name', 'Unknown')} ({p.get('role', 'Unknown role')}): "
            f"{p.get('current_work', '')}. Follow-up: {p.get('follow_up', 'None')}"
            for p in people
        )
        parts.append(f"ATTENDEES AND THEIR WORK:\n{people_text}")

    if knowledge_chunks:
        kb_text = "\n---\n".join(knowledge_chunks[:8])  # limit to 8 chunks
        parts.append(f"PREVIOUS MEETING CONTEXT:\n{kb_text}")

    if jira_tickets:
        jira_text = "\n".join(
            f"- {t['key']}: {t['summary']} [{t['status']}] Owner: {t.get('assignee', 'unassigned')} "
            f"Blockers: {', '.join(t.get('blockers', [])) or 'none'}"
            for t in jira_tickets
        )
        parts.append(f"OPEN JIRA TICKETS:\n{jira_text}")

    if context.get("previous_summary"):
        parts.append(f"PREVIOUS MEETING SUMMARY:\n{context['previous_summary']}")

    if context.get("open_action_items"):
        items_text = "\n".join(f"- {item}" for item in context["open_action_items"])
        parts.append(f"OPEN ACTION ITEMS:\n{items_text}")

    return "\n\n".join(parts)
