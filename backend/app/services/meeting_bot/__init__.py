from __future__ import annotations

import asyncio

from app.services.meeting_bot.base import (
    BotInfo,
    BotStatus,
    MeetingBotProvider,
    TranscriptSegment,
)


class MockMeetingBotProvider(MeetingBotProvider):
    """
    Mock meeting bot provider for local development.
    Simulates a bot joining a meeting and providing transcript segments.
    """

    _MOCK_BOT_ID = "mock-bot-00000001"

    _MOCK_TRANSCRIPT = [
        TranscriptSegment("John Smith", "Good morning everyone, let's get started.", 1000, True),
        TranscriptSegment("Sarah Chen", "Hi everyone! Ready to review the dashboard status.", 5000, True),
        TranscriptSegment("David Lee", "The client is quite eager to see the progress today.", 10000, True),
        TranscriptSegment(
            "John Smith",
            "The API authentication work is done and all tests are passing. "
            "We can unblock the frontend now.",
            15000,
            True,
        ),
        TranscriptSegment(
            "Sarah Chen",
            "Dashboard design is in final review — I'll get client approval today.",
            25000,
            True,
        ),
        TranscriptSegment(
            "John Smith",
            "One issue: the deployment pipeline is still flaky. "
            "I'm owning that fix, targeting end of week.",
            35000,
            True,
        ),
        TranscriptSegment("David Lee", "Is June 15th still realistic for delivery?", 45000, True),
        TranscriptSegment(
            "Sarah Chen",
            "Yes, if we get client sign-off this week and the pipeline is stable, we're on track.",
            52000,
            True,
        ),
    ]

    async def create_bot(
        self,
        meeting_url: str,
        bot_name: str = "AmMeeting",
        webhook_url: str | None = None,
    ) -> BotInfo:
        await asyncio.sleep(0.5)
        return BotInfo(
            bot_id=self._MOCK_BOT_ID,
            status=BotStatus.IN_MEETING,
            meeting_url=meeting_url,
            provider="mock",
            raw={"id": self._MOCK_BOT_ID, "mock": True},
        )

    async def get_bot_status(self, bot_id: str) -> BotInfo:
        await asyncio.sleep(0.1)
        return BotInfo(
            bot_id=bot_id,
            status=BotStatus.IN_MEETING,
            meeting_url="https://zoom.us/j/mock",
            provider="mock",
            raw={"id": bot_id, "status": "in_meeting", "mock": True},
        )

    async def leave_meeting(self, bot_id: str) -> bool:
        await asyncio.sleep(0.2)
        return True

    async def speak_message(self, bot_id: str, text: str) -> bool:
        await asyncio.sleep(0.3)
        return True

    async def get_transcript(self, bot_id: str) -> list[TranscriptSegment]:
        await asyncio.sleep(0.1)
        return list(self._MOCK_TRANSCRIPT)


def get_bot_provider() -> MeetingBotProvider:
    """Factory: returns the configured meeting bot provider."""
    from app.core.config import get_settings
    settings = get_settings()

    if settings.bot_provider == "recall":
        if not settings.recall_api_key:
            raise ValueError(
                "RECALL_API_KEY is not set. "
                "Set bot_provider=mock to use the mock provider."
            )
        from app.services.meeting_bot.recall import RecallAIBotProvider
        return RecallAIBotProvider()

    return MockMeetingBotProvider()
