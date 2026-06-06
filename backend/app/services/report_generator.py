from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.meeting import (
    ActionItem,
    Answer,
    Decision,
    Meeting,
    Question,
    QuestionStatus,
    Report,
    Risk,
)
from app.services.integrations import get_slack
from app.services.llm import get_llm

_logger = get_logger(__name__)

_REPORT_SYSTEM = """You are AmMeeting's report generator. Create a structured meeting report.

Based on the provided meeting data, generate:
1. A concise executive summary (3-5 sentences)
2. A follow-up email draft
3. A Slack message draft (brief, 2-3 bullet points)
4. Suggested Jira ticket updates

Return JSON:
{
  "summary": str,
  "follow_up_recommendations": [str],
  "email_draft": str,
  "slack_draft": str,
  "jira_suggestions": [{"ticket_key": str | null, "action": str, "notes": str}],
  "next_meeting_agenda": [str]
}"""


async def generate_report(db: AsyncSession, meeting: Meeting) -> Report:
    """Generate a full post-meeting report."""
    # Gather all meeting data
    questions_result = await db.execute(select(Question).where(Question.meeting_id == meeting.id))
    questions = list(questions_result.scalars().all())

    answers_result = await db.execute(select(Answer).where(Answer.meeting_id == meeting.id))
    answers = list(answers_result.scalars().all())

    action_items_result = await db.execute(select(ActionItem).where(ActionItem.meeting_id == meeting.id))
    action_items = list(action_items_result.scalars().all())

    decisions_result = await db.execute(select(Decision).where(Decision.meeting_id == meeting.id))
    decisions = list(decisions_result.scalars().all())

    risks_result = await db.execute(select(Risk).where(Risk.meeting_id == meeting.id))
    risks = list(risks_result.scalars().all())

    # Build context for LLM
    qa_pairs = []
    answer_map = {a.question_id: a for a in answers if a.question_id}
    for q in questions:
        a = answer_map.get(q.id)
        qa_pairs.append({
            "question": q.text,
            "status": q.status,
            "answer": a.text if a else None,
            "category": q.category,
        })

    unanswered = [q for q in questions if q.status not in (QuestionStatus.ANSWERED,)]

    meeting_data = {
        "title": meeting.title,
        "purpose": meeting.purpose,
        "mode": meeting.mode,
        "qa_pairs": qa_pairs[:20],
        "action_items": [{"title": ai.title, "owner": ai.owner, "deadline": ai.deadline} for ai in action_items],
        "decisions": [{"text": d.text, "made_by": d.made_by} for d in decisions],
        "risks": [{"text": r.text, "severity": r.severity} for r in risks],
        "unanswered_questions": [q.text for q in unanswered],
    }

    llm = get_llm()
    try:
        llm_result = await llm.complete_json(
            system=_REPORT_SYSTEM,
            user=f"Generate a meeting report for:\n\n{json.dumps(meeting_data, indent=2)}",
        )
    except Exception as exc:
        _logger.error("Report generation LLM call failed: %s", exc)
        llm_result = {
            "summary": f"Meeting '{meeting.title}' completed. {len(answers)} questions answered, {len(action_items)} action items identified.",
            "follow_up_recommendations": ["Review open action items", "Schedule follow-up meeting"],
            "email_draft": f"Hi team,\n\nPlease find the summary from our meeting '{meeting.title}' attached.\n\nBest regards",
            "slack_draft": f"Meeting summary for *{meeting.title}*:\n• {len(answers)} items answered\n• {len(action_items)} action items\n• {len(unanswered)} questions pending",
            "jira_suggestions": [],
            "next_meeting_agenda": ["Review action item progress", "Address unanswered questions"],
        }

    full_data = {
        **meeting_data,
        **llm_result,
        "report_generated_by": "AmMeeting",
    }

    # Check for existing report
    existing = await db.execute(select(Report).where(Report.meeting_id == meeting.id))
    report = existing.scalar_one_or_none()

    if report is None:
        report = Report(
            meeting_id=meeting.id,
            workspace_id=meeting.workspace_id,
        )
        db.add(report)

    report.summary = llm_result.get("summary", "")
    report.full_json = json.dumps(full_data)
    report.slack_draft = llm_result.get("slack_draft", "")
    report.email_draft = llm_result.get("email_draft", "")
    report.jira_draft = json.dumps(llm_result.get("jira_suggestions", []))

    await db.flush()
    return report


async def send_slack_draft(db: AsyncSession, report: Report, channel: str) -> dict:
    """Send Slack draft — requires explicit user review/trigger."""
    if not report.slack_draft:
        return {"error": "No Slack draft available"}
    slack = get_slack()
    result = await slack.send_message(channel, report.slack_draft)
    report.slack_sent = True
    await db.flush()
    return result
