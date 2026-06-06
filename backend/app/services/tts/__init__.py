from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from functools import lru_cache

from app.services.tts.base import TTSProvider


class MockTTSProvider(TTSProvider):
    """Mock TTS — returns empty bytes (silent). Used when no TTS key configured."""

    async def synthesize(self, text: str) -> bytes:
        await asyncio.sleep(0.05)
        _len = min(len(text) * 100, 10000)
        # Return a minimal valid-length dummy byte sequence so callers can detect output
        return b"\x00" * _len

    async def synthesize_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        audio = await self.synthesize(text)
        chunk = 4096
        for i in range(0, len(audio), chunk):
            yield audio[i : i + chunk]
            await asyncio.sleep(0.01)

    @property
    def audio_format(self) -> str:
        return "pcm"

    @property
    def sample_rate(self) -> int:
        return 16000


@lru_cache(maxsize=1)
def get_tts() -> TTSProvider:
    """Factory: returns the configured TTS provider."""
    from app.core.config import get_settings
    settings = get_settings()

    if settings.tts_provider == "openai":
        if not settings.openai_api_key:
            import logging
            logging.getLogger(__name__).warning(
                "OPENAI_API_KEY not set; falling back to mock TTS."
            )
            return MockTTSProvider()
        from app.services.tts.openai_tts import OpenAITTSProvider
        return OpenAITTSProvider()

    return MockTTSProvider()
