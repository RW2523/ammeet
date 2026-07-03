from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.services.llm import get_llm

_logger = get_logger(__name__)

# Patterns that require human escalation
_RESTRICTED_PATTERNS = [
    r"\b(budget|approve|approval|contract|legal|liable|liability|lawsuit|hire|fire|terminat|performance review)\b",
    r"\b(final decision|commit|commitment|agree to|sign|binding|non-disclosure|nda)\b",
    r"\b(salary|compensation|bonus|raise|layoff|restructur)\b",
    r"\b(medical|health|confidential|sensitive personal)\b",
    r"\b(lawsuit|litigation|regulatory|compliance violation)\b",
]

_RESTRICTED_RE = re.compile("|".join(_RESTRICTED_PATTERNS), re.IGNORECASE)

_ESCALATION_SYSTEM = """You are a safety classifier for AmMeeting, an AI meeting assistant.

Determine if the following meeting content requires human escalation.

Escalation is required if:
- Budget, financial commitments, or approvals are being discussed
- Legal, contractual, or compliance matters appear
- HR decisions (hiring, firing, performance) are being discussed
- Someone is asking for a final decision or commitment
- Sensitive personal data is mentioned
- The AI's confidence would be low for this topic

Return JSON: {"requires_escalation": bool, "reason": str | null, "confidence": float}"""


async def classify_escalation(text: str) -> dict[str, Any]:
    """Classify whether a piece of meeting content requires human escalation."""
    # Fast regex check first
    if _RESTRICTED_RE.search(text):
        return {
            "requires_escalation": True,
            "reason": "Restricted topic detected (budget/legal/HR/commitment)",
            "confidence": 0.95,
        }

    # LLM fallback for subtle cases
    try:
        llm = get_llm()
        result = await llm.complete_json(
            system=_ESCALATION_SYSTEM,
            user=f"Classify this meeting content:\n\n{text[:2000]}",
        )
        return result
    except Exception as exc:
        _logger.warning("Escalation classification LLM call failed: %s", exc)
        # FAIL CLOSED: if the safety classifier is unavailable we cannot rule out a
        # restricted topic, so route to a human rather than let the AI proceed.
        return {
            "requires_escalation": True,
            "reason": "Safety classifier unavailable — defaulting to human review",
            "confidence": 0.0,
        }


def is_restricted_topic(text: str) -> bool:
    """Fast synchronous check for obviously restricted topics."""
    return bool(_RESTRICTED_RE.search(text))
