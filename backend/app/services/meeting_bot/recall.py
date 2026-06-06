from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.meeting_bot.base import (
    BotInfo,
    BotStatus,
    MeetingBotProvider,
    TranscriptSegment,
)

_logger = get_logger(__name__)
_settings = get_settings()

# Recall.ai status → our BotStatus mapping
_STATUS_MAP: dict[str, BotStatus] = {
    "ready": BotStatus.CREATED,
    "joining_call": BotStatus.JOINING,
    "in_waiting_room": BotStatus.JOINING,
    "in_call_not_recording": BotStatus.IN_MEETING,
    "in_call_recording": BotStatus.IN_MEETING,
    "call_ended": BotStatus.DONE,
    "done": BotStatus.DONE,
    "error": BotStatus.ERROR,
    "fatal": BotStatus.ERROR,
}


class RecallAIBotProvider(MeetingBotProvider):
    """
    Recall.ai meeting bot provider.
    Creates bots that join Zoom, Google Meet, and Microsoft Teams meetings.

    Recall.ai API docs: https://docs.recall.ai

    Required env var: RECALL_API_KEY
    Optional:        RECALL_API_BASE (defaults to us-east-1 region)

    Features used:
    - POST  /bot/            — create + deploy bot
    - GET   /bot/{id}/       — get bot status
    - POST  /bot/{id}/leave_call/  — remove bot from meeting
    - GET   /bot/{id}/transcript/  — get transcript
    - POST  /bot/{id}/speak_message/ — make bot speak (TTS injection)
    """

    def __init__(self) -> None:
        api_key = _settings.recall_api_key
        if not api_key:
            raise ValueError(
                "RECALL_API_KEY is not set. "
                "Set bot_provider=mock to use the mock provider."
            )

        self._client = httpx.AsyncClient(
            base_url=_settings.recall_api_base.rstrip("/") + "/",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    async def create_bot(
        self,
        meeting_url: str,
        bot_name: str = "AmMeeting",
        webhook_url: str | None = None,
    ) -> BotInfo:
        """Create and deploy a Recall.ai bot to the given meeting URL."""
        payload: dict[str, Any] = {
            "meeting_url": meeting_url,
            "bot_name": bot_name,
            "transcription_options": {
                "provider": "assembly_ai",
            },
            "chat": {
                "on_bot_join": {
                    "send_to": "everyone",
                    "message": (
                        f"👋 Hi! {bot_name} (AI assistant) has joined this meeting "
                        "as an authorized representative. I'll be asking follow-up questions "
                        "and collecting updates. I won't make any commitments or decisions."
                    ),
                }
            },
        }

        if webhook_url:
            payload["webhook_url"] = webhook_url

        _logger.info("Creating Recall.ai bot for meeting: %s", meeting_url)
        resp = await self._client.post("bot/", json=payload)
        resp.raise_for_status()
        data = resp.json()
        _logger.info("Recall.ai bot created: %s", data.get("id"))

        return BotInfo(
            bot_id=data["id"],
            status=_STATUS_MAP.get(data.get("status_changes", [{}])[-1].get("code", ""), BotStatus.CREATED),
            meeting_url=meeting_url,
            provider="recall",
            raw=data,
        )

    async def get_bot_status(self, bot_id: str) -> BotInfo:
        """Get current status of a Recall.ai bot."""
        resp = await self._client.get(f"bot/{bot_id}/")
        resp.raise_for_status()
        data = resp.json()

        status_changes = data.get("status_changes", [])
        latest_status = status_changes[-1].get("code", "ready") if status_changes else "ready"

        return BotInfo(
            bot_id=bot_id,
            status=_STATUS_MAP.get(latest_status, BotStatus.CREATED),
            meeting_url=data.get("meeting_url", ""),
            provider="recall",
            raw=data,
        )

    async def leave_meeting(self, bot_id: str) -> bool:
        """Remove the bot from the meeting."""
        _logger.info("Removing Recall.ai bot %s from meeting", bot_id)
        try:
            resp = await self._client.post(f"bot/{bot_id}/leave_call/")
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            _logger.error("Failed to remove bot %s: %s", bot_id, exc.response.text)
            return False

    async def speak_message(self, bot_id: str, text: str) -> bool:
        """
        Make the Recall.ai bot speak a message in the meeting.
        Recall.ai handles TTS internally.
        """
        if not text or not text.strip():
            return True

        _logger.info("Bot %s speaking: %s...", bot_id, text[:80])
        try:
            resp = await self._client.post(
                f"bot/{bot_id}/speak_message/",
                json={"message": text.strip()},
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            _logger.error(
                "Bot speak failed for %s (%d): %s",
                bot_id,
                exc.response.status_code,
                exc.response.text,
            )
            return False

    async def get_transcript(self, bot_id: str) -> list[TranscriptSegment]:
        """Get transcript segments from a Recall.ai bot."""
        resp = await self._client.get(f"bot/{bot_id}/transcript/")
        resp.raise_for_status()
        data = resp.json()

        segments: list[TranscriptSegment] = []
        # Recall.ai transcript format: list of word/sentence objects
        for item in data:
            speaker = item.get("speaker", "Unknown")
            words = item.get("words", [])
            if words:
                text = " ".join(w.get("text", "") for w in words)
                start_ms = int(words[0].get("start_time", 0) * 1000)
                segments.append(
                    TranscriptSegment(
                        speaker=speaker,
                        text=text.strip(),
                        timestamp_ms=start_ms,
                        is_final=True,
                    )
                )

        return segments

    async def close(self) -> None:
        await self._client.aclose()
