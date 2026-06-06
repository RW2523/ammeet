from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class TTSProvider(ABC):
    """Text-to-speech provider interface."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Convert text to audio bytes (MP3 by default)."""
        ...

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """Stream audio bytes as they are generated."""
        ...

    @property
    @abstractmethod
    def audio_format(self) -> str:
        """Returns the audio format: 'mp3', 'wav', 'pcm', etc."""
        ...

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Returns the audio sample rate in Hz."""
        ...
