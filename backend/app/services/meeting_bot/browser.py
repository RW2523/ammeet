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

_STATUS_MAP: dict[str, BotStatus] = {
    "created": BotStatus.CREATED,
    "joining": BotStatus.JOINING,
    "in_meeting": BotStatus.IN_MEETING,
    "done": BotStatus.DONE,
    "error": BotStatus.ERROR,
}


class BrowserBotProvider(MeetingBotProvider):
    """Self-hosted meeting bot: drives the `bot-worker` microservice (headless Chromium
    + Playwright) that actually joins Zoom/Meet/Teams/Jitsi calls. Same interface as
    the Recall provider, so the proxy engine and assistant agent use it unchanged.

    The worker reports transcript to AmMeeting's /api/webhooks/recall/{meeting_id}
    endpoint in the same shape Recall uses, so ingestion is identical.
    """

    def __init__(self) -> None:
        self._base = _settings.browser_bot_worker_url.rstrip("/")

    async def create_bot(
        self, meeting_url: str, bot_name: str = "AmMeeting", webhook_url: str | None = None
    ) -> BotInfo:
        _logger.info("Deploying browser bot to %s", meeting_url)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base}/bots",
                json={"meeting_url": meeting_url, "display_name": bot_name, "webhook_url": webhook_url},
            )
            resp.raise_for_status()
            data = resp.json()
        return BotInfo(
            bot_id=data["id"],
            status=_STATUS_MAP.get(data.get("status", "joining"), BotStatus.JOINING),
            meeting_url=meeting_url,
            provider="browser",
            raw=data,
        )

    async def get_bot_status(self, bot_id: str) -> BotInfo:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self._base}/bots/{bot_id}")
            resp.raise_for_status()
            data = resp.json()
        return BotInfo(
            bot_id=bot_id,
            status=_STATUS_MAP.get(data.get("status", "created"), BotStatus.CREATED),
            meeting_url=data.get("meeting_url", ""),
            provider="browser",
            raw=data,
        )

    async def leave_meeting(self, bot_id: str) -> bool:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._base}/bots/{bot_id}/leave")
            return resp.status_code == 200

    async def output_audio(self, bot_id: str, mp3_bytes: bytes) -> bool:
        if not mp3_bytes:
            return True
        b64 = base64.b64encode(mp3_bytes).decode("utf-8")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self._base}/bots/{bot_id}/output-audio", json={"b64": b64})
            if resp.status_code != 200:
                return False
            return bool(resp.json().get("ok"))

    async def get_transcript(self, bot_id: str) -> list[TranscriptSegment]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self._base}/bots/{bot_id}/transcript")
            resp.raise_for_status()
            segments = resp.json().get("segments", [])
        return [
            TranscriptSegment(
                speaker=s.get("speaker", "Participant"),
                text=s.get("text", ""),
                timestamp_ms=int(s.get("timestamp_ms", 0)),
                is_final=True,
            )
            for s in segments
        ]
