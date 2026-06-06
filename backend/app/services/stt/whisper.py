from __future__ import annotations

import os
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.stt.base import STTProvider

_logger = get_logger(__name__)
_settings = get_settings()

# Supported audio formats for Whisper
WHISPER_SUPPORTED_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".flac"}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB Whisper limit


class WhisperSTTProvider(STTProvider):
    """
    Real OpenAI Whisper transcription provider.
    Uses the /audio/transcriptions endpoint.
    Supports: mp3, mp4, mpeg, mpga, m4a, wav, webm, ogg, flac.
    Max file size: 25 MB.
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {_settings.openai_api_key}"},
            timeout=120.0,
        )

    async def transcribe(self, audio_path: str) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        ext = path.suffix.lower()
        if ext not in WHISPER_SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported audio format '{ext}'. "
                f"Supported: {', '.join(WHISPER_SUPPORTED_EXTENSIONS)}"
            )

        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"Audio file too large ({file_size / 1024 / 1024:.1f} MB). "
                f"Whisper limit is 25 MB."
            )

        _logger.info("Transcribing %s (%d bytes) with Whisper", path.name, file_size)

        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        return await self._transcribe_bytes_impl(audio_bytes, path.name, ext)

    async def transcribe_bytes(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        ext = os.path.splitext(filename)[1].lower() or ".wav"
        if ext not in WHISPER_SUPPORTED_EXTENSIONS:
            ext = ".wav"
        return await self._transcribe_bytes_impl(audio_bytes, filename, ext)

    async def _transcribe_bytes_impl(self, audio_bytes: bytes, filename: str, ext: str) -> str:
        mime_types = {
            ".mp3": "audio/mpeg",
            ".mp4": "audio/mp4",
            ".mpeg": "audio/mpeg",
            ".mpga": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".webm": "audio/webm",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
        }
        mime = mime_types.get(ext, "audio/wav")
        try:
            resp = await self._client.post(
                "/audio/transcriptions",
                files={"file": (filename, audio_bytes, mime)},
                data={"model": "whisper-1", "response_format": "text"},
            )
            resp.raise_for_status()
            transcript = resp.text.strip()
            _logger.info("Whisper transcription complete: %d chars", len(transcript))
            return transcript
        except httpx.HTTPStatusError as exc:
            _logger.error(
                "Whisper API error %d: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise
        except Exception as exc:
            _logger.error("Whisper transcription failed: %s", exc)
            raise

    async def close(self) -> None:
        await self._client.aclose()
