from __future__ import annotations

import base64
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

# A ~0.2s silent MP3. Recall requires `automatic_audio_output` to be configured at
# bot-creation time to enable the on-demand /output_audio/ endpoint; we seed it with
# silence so the bot doesn't auto-play anything but can speak on command later.
_SILENT_MP3_B64 = (
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYyLjEyLjEwMQAAAAAAAAAAAAAA//OEwAAAAAAAAAAAAElu"
    "Zm8AAAAPAAAACwAAAcgAeXl5eXl5eXl5hoaGhoaGhoaGlJSUlJSUlJSUoaGhoaGhoaGhr6+vr6+vr6+"
    "vvLy8vLy8vLy8ysrKysrKysrK19fX19fX19fX5eXl5eXl5eXl8vLy8vLy8vLy////////////AAAAAExh"
    "dmM2Mi4yOAAAAAAAAAAAAAAAACQDwAAAAAAAAAHIPuBHcQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//MU"
    "xAAAAANIAAAAAExBTUUzLjEwMFVV//MUxAsAAANIAAAAAFVVVVVVVVVVVVVV//MUxBYAAANIAAAAAFVV"
    "VVVVVVVVVVVV//MUxCEAAANIAAAAAFVVVVVVVVVVVVVV//MUxCwAAANIAAAAAFVVVVVVVVVVVVVV//MU"
    "xDcAAANIAAAAAFVVVVVVVVVVVVVV//MUxEIAAANIAAAAAFVVVVVVVVVVVVVV//MUxE0AAANIAAAAAFVV"
    "VVVVVVVVVVVV//MUxFgAAANIAAAAAFVVVVVVVVVVVVVV//MUxGMAAANIAAAAAFVVVVVVVVVVVVVV//MU"
    "xG4AAANIAAAAAFVVVVVVVVVVVVVV"
)

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
            # Required to enable the on-demand /output_audio/ endpoint. Seeded with
            # silence so nothing auto-plays; real speech is sent later via output_audio().
            "automatic_audio_output": {
                "in_call_recording": {
                    "data": {"kind": "mp3", "b64_data": _SILENT_MP3_B64}
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

        # status_changes may be present-but-empty on a freshly created bot
        status_changes = data.get("status_changes") or [{}]
        return BotInfo(
            bot_id=data["id"],
            status=_STATUS_MAP.get(status_changes[-1].get("code", ""), BotStatus.CREATED),
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

    async def output_audio(self, bot_id: str, mp3_bytes: bytes) -> bool:
        """
        Play synthesized speech (MP3 bytes) into the live meeting via Recall.ai's
        Output Audio API, so other participants actually hear it.

        POST /bot/{id}/output_audio/  body: {"kind": "mp3", "b64_data": <base64 mp3>}
        Requires the bot to have been created with `automatic_audio_output`.
        """
        if not mp3_bytes:
            return True

        b64 = base64.b64encode(mp3_bytes).decode("utf-8")
        _logger.info("Bot %s outputting %d bytes of audio into meeting", bot_id, len(mp3_bytes))
        try:
            resp = await self._client.post(
                f"bot/{bot_id}/output_audio/",
                json={"kind": "mp3", "b64_data": b64},
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPStatusError as exc:
            _logger.error(
                "Bot output_audio failed for %s (%d): %s",
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
