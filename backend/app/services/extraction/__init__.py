from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.services.llm import get_llm

_logger = get_logger(__name__)

_EXTRACTION_SYSTEM = """You are an expert meeting analyst. Extract structured information from meeting transcripts and notes.

Return a JSON object with these exact keys:
{
  "people": [{"name": str, "role": str | null, "email": str | null}],
  "topics": [str],
  "decisions": [{"text": str, "made_by": str | null, "requires_approval": bool}],
  "action_items": [{"title": str, "owner": str | null, "deadline": str | null}],
  "risks": [{"text": str, "severity": "low"|"medium"|"high"}],
  "pending_questions": [str],
  "blockers": [str],
  "summary": str
}

Be thorough but concise. Extract only information explicitly stated or clearly implied."""


async def extract_from_text(text: str) -> dict[str, Any]:
    """Extract structured meeting data from raw text using LLM."""
    llm = get_llm()
    try:
        result = await llm.complete_json(
            system=_EXTRACTION_SYSTEM,
            user=f"Extract structured information from this meeting content:\n\n{text[:12000]}",
        )
        return result
    except Exception as exc:
        _logger.error("Extraction failed: %s", exc)
        return {
            "people": [],
            "topics": [],
            "decisions": [],
            "action_items": [],
            "risks": [],
            "pending_questions": [],
            "blockers": [],
            "summary": "Extraction failed. Please review manually.",
        }


async def chunk_text(text: str, chunk_size: int = 500) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    words = text.split()
    chunks: list[str] = []
    step = int(chunk_size * 0.85)  # 15% overlap
    for i in range(0, max(1, len(words)), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks
