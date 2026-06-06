from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text. Returns full transcript."""
        ...

    async def transcribe_bytes(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        """Transcribe raw audio bytes. Override for providers that support it."""
        import tempfile
        import os
        suffix = os.path.splitext(filename)[1] or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        try:
            return await self.transcribe(tmp_path)
        finally:
            os.unlink(tmp_path)


class RealtimeSTTProvider(STTProvider):
    """Extended interface for providers that support real-time streaming transcription."""

    async def stream_transcribe(self, audio_stream: AsyncGenerator[bytes, None]) -> AsyncGenerator[str, None]:
        """Stream audio chunks and yield partial transcript strings."""
        # Default: collect all chunks then transcribe
        chunks: list[bytes] = []
        async for chunk in audio_stream:
            chunks.append(chunk)
        full_audio = b"".join(chunks)
        transcript = await self.transcribe_bytes(full_audio)
        yield transcript
