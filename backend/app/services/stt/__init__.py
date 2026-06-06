from __future__ import annotations

import asyncio

from app.services.stt.base import STTProvider, RealtimeSTTProvider


class MockSTTProvider(RealtimeSTTProvider):
    """
    Mock STT — returns a realistic fixture transcript.
    Used for local dev without API keys.
    """

    _FIXTURE = (
        "John: The API authentication issue has been resolved. "
        "We deployed the fix yesterday and all tests are passing. "
        "Sarah: Great news. The frontend team can start integration on Monday. "
        "David: The client is asking for final confirmation on the dashboard design. "
        "Can we get that approved this week? "
        "Sarah: I'll follow up with the client today. "
        "John: One concern — the deployment pipeline is still flaky on staging. "
        "We might need to address that before the release. "
        "David: That's a risk we should flag. Who owns the pipeline fix? "
        "John: I'll take ownership. Target is end of this week. "
        "Sarah: Good. Let's confirm the June 15 delivery date is still achievable."
    )

    async def transcribe(self, audio_path: str) -> str:
        await asyncio.sleep(0.2)
        return self._FIXTURE


def get_stt() -> STTProvider:
    """Factory: returns the configured STT provider."""
    from app.core.config import get_settings
    settings = get_settings()

    if settings.stt_provider == "whisper":
        if not settings.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY required for stt_provider=whisper. "
                "Set stt_provider=mock to use the mock provider."
            )
        from app.services.stt.whisper import WhisperSTTProvider
        return WhisperSTTProvider()

    if settings.stt_provider == "assemblyai":
        if not settings.assemblyai_api_key:
            raise ValueError(
                "ASSEMBLYAI_API_KEY required for stt_provider=assemblyai. "
                "Set stt_provider=mock to use the mock provider."
            )
        from app.services.stt.assemblyai_realtime import AssemblyAIRealtimeSTT
        return AssemblyAIRealtimeSTT()

    return MockSTTProvider()


def get_realtime_stt() -> RealtimeSTTProvider:
    """Factory: returns a real-time capable STT provider."""
    from app.core.config import get_settings
    settings = get_settings()

    if settings.stt_provider == "assemblyai":
        from app.services.stt.assemblyai_realtime import AssemblyAIRealtimeSTT
        return AssemblyAIRealtimeSTT()

    # Whisper and mock both work via transcribe_bytes (collect-then-transcribe)
    return MockSTTProvider()
