from __future__ import annotations

import asyncio

from app.services.stt.base import STTProvider


class MockSTTProvider(STTProvider):
    """
    Stub STT provider — returns realistic fixture transcript.
    Swap for real Whisper/AssemblyAI impl in a later phase.
    """

    _FIXTURE = (
        "John: The API authentication issue has been resolved. "
        "We deployed the fix yesterday and tests are passing. "
        "Sarah: Great. The frontend team can start integration on Monday. "
        "David: The client is asking for confirmation on the dashboard design. "
        "Can we get that approved this week? "
        "Sarah: I'll follow up with the client today. "
        "John: One concern — the deployment pipeline is still flaky. "
        "We might need to address that before the release date. "
        "David: That's a risk we should flag. Who owns the pipeline fix? "
        "John: I'll take ownership. Target is end of this week."
    )

    async def transcribe(self, audio_path: str) -> str:
        await asyncio.sleep(0.1)
        return self._FIXTURE


def get_stt() -> STTProvider:
    from app.core.config import get_settings
    settings = get_settings()
    if settings.stt_provider == "real":
        raise NotImplementedError("Real STT provider not yet implemented.")
    return MockSTTProvider()
