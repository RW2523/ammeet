from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class BotStatus(str, Enum):
    CREATED = "created"
    JOINING = "joining"
    IN_MEETING = "in_meeting"
    LEAVING = "leaving"
    DONE = "done"
    ERROR = "error"


@dataclass
class TranscriptSegment:
    speaker: str
    text: str
    timestamp_ms: int
    is_final: bool


@dataclass
class BotInfo:
    bot_id: str
    status: BotStatus
    meeting_url: str
    provider: str
    raw: dict[str, Any]


class MeetingBotProvider(ABC):
    """Abstract meeting bot provider interface."""

    @abstractmethod
    async def create_bot(
        self,
        meeting_url: str,
        bot_name: str = "AmMeeting",
        webhook_url: str | None = None,
    ) -> BotInfo:
        """Create and deploy a bot to join the given meeting URL."""
        ...

    @abstractmethod
    async def get_bot_status(self, bot_id: str) -> BotInfo:
        """Get current bot status."""
        ...

    @abstractmethod
    async def leave_meeting(self, bot_id: str) -> bool:
        """Remove the bot from the meeting."""
        ...

    @abstractmethod
    async def speak_message(self, bot_id: str, text: str) -> bool:
        """Make the bot speak a message in the meeting via TTS injection."""
        ...

    @abstractmethod
    async def get_transcript(self, bot_id: str) -> list[TranscriptSegment]:
        """Get all transcript segments collected so far."""
        ...
