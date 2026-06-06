from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncGenerator
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.stt.base import RealtimeSTTProvider

_logger = get_logger(__name__)
_settings = get_settings()

ASSEMBLYAI_REALTIME_URL = "wss://api.assemblyai.com/v2/realtime/ws"
CHUNK_SIZE = 4096  # bytes per audio chunk sent to AssemblyAI


class AssemblyAIRealtimeSTT(RealtimeSTTProvider):
    """
    Real-time streaming transcription via AssemblyAI WebSocket API.
    Streams audio chunks and yields partial/final transcript strings.

    AssemblyAI real-time protocol:
    - Connect to WSS endpoint with Authorization header
    - Send: {"audio_data": "<base64 encoded audio chunk>"}
    - Receive: {"message_type": "PartialTranscript"|"FinalTranscript", "text": "..."}
    """

    def __init__(self) -> None:
        if not _settings.assemblyai_api_key:
            raise ValueError(
                "ASSEMBLYAI_API_KEY is not set. "
                "Set stt_provider=mock to use the mock provider."
            )
        self._api_key = _settings.assemblyai_api_key

    async def transcribe(self, audio_path: str) -> str:
        """Transcribe a file using AssemblyAI synchronous API (fallback for files)."""
        import httpx
        from pathlib import Path

        path = Path(audio_path)
        with open(path, "rb") as f:
            audio_bytes = f.read()

        async with httpx.AsyncClient(
            base_url="https://api.assemblyai.com",
            headers={"Authorization": self._api_key},
            timeout=120.0,
        ) as client:
            # Upload file
            upload_resp = await client.post(
                "/v2/upload",
                content=audio_bytes,
                headers={"Content-Type": "application/octet-stream"},
            )
            upload_resp.raise_for_status()
            upload_url = upload_resp.json()["upload_url"]

            # Request transcription
            transcript_resp = await client.post(
                "/v2/transcript",
                json={"audio_url": upload_url},
            )
            transcript_resp.raise_for_status()
            transcript_id = transcript_resp.json()["id"]

            # Poll until complete
            while True:
                status_resp = await client.get(f"/v2/transcript/{transcript_id}")
                status_resp.raise_for_status()
                data = status_resp.json()
                if data["status"] == "completed":
                    return data.get("text", "")
                if data["status"] == "error":
                    raise RuntimeError(f"AssemblyAI transcription error: {data.get('error')}")
                await asyncio.sleep(2)

    async def stream_transcribe(
        self,
        audio_stream: AsyncGenerator[bytes, None],
    ) -> AsyncGenerator[str, None]:
        """
        Stream audio chunks to AssemblyAI and yield transcript text in real time.
        Yields final transcript segments as they are confirmed.
        """
        try:
            import websockets
        except ImportError:
            raise RuntimeError("websockets library not installed. Run: pip install websockets")

        url = f"{ASSEMBLYAI_REALTIME_URL}?sample_rate=16000&encoding=pcm_s16le"
        headers = [("Authorization", self._api_key)]

        _logger.info("Connecting to AssemblyAI real-time WebSocket")

        # Buffer for transcript segments
        transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        done_event = asyncio.Event()

        async def _receive_transcripts(ws: Any) -> None:
            """Receive transcript messages from AssemblyAI."""
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    msg_type = msg.get("message_type", "")
                    text = msg.get("text", "").strip()

                    if msg_type == "SessionBegins":
                        _logger.info("AssemblyAI session started: %s", msg.get("session_id"))

                    elif msg_type == "FinalTranscript" and text:
                        _logger.debug("AssemblyAI final: %s", text)
                        await transcript_queue.put(text)

                    elif msg_type == "SessionTerminated":
                        _logger.info("AssemblyAI session terminated")
                        break

            except Exception as exc:
                _logger.error("AssemblyAI receive error: %s", exc)
            finally:
                done_event.set()

        async def _send_audio(ws: Any) -> None:
            """Send audio chunks to AssemblyAI."""
            try:
                async for chunk in audio_stream:
                    if not chunk:
                        continue
                    # AssemblyAI expects base64 encoded chunks
                    encoded = base64.b64encode(chunk).decode("utf-8")
                    await ws.send(json.dumps({"audio_data": encoded}))
                # Signal end of audio
                await ws.send(json.dumps({"terminate_session": True}))
            except Exception as exc:
                _logger.error("AssemblyAI send error: %s", exc)

        async with websockets.connect(
            url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            # Run send + receive concurrently
            send_task = asyncio.create_task(_send_audio(ws))
            recv_task = asyncio.create_task(_receive_transcripts(ws))

            # Yield transcripts as they arrive
            while not done_event.is_set() or not transcript_queue.empty():
                try:
                    text = await asyncio.wait_for(transcript_queue.get(), timeout=0.5)
                    yield text
                except asyncio.TimeoutError:
                    continue

            await send_task
            await recv_task


class AssemblyAIBatchSTT(AssemblyAIRealtimeSTT):
    """File-based (batch) AssemblyAI transcription only."""
    pass
