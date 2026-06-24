from __future__ import annotations

"""
Live session router:
  - WebSocket  /api/ws/meetings/{meeting_id}      — real-time event stream to browser
  - POST       /api/webhooks/recall/{meeting_id}  — Recall.ai webhook receiver
  - GET        /api/workspaces/{wid}/meetings/{mid}/bot/status — bot status
  - POST       /api/workspaces/{wid}/meetings/{mid}/bot/join   — join meeting
  - POST       /api/workspaces/{wid}/meetings/{mid}/bot/leave  — leave meeting
  - POST       /api/workspaces/{wid}/meetings/{mid}/transcribe-audio — upload audio for Whisper
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_workspace_role
from app.core.redis import get_redis
from app.models.meeting import Meeting, MeetingMode, MeetingStatus, Question, QuestionStatus
from app.models.meeting_bot import BotStatus, MeetingBot
from app.models.user import AuditLog, User, WorkspaceRole
from app.services.live_proxy import (
    get_active_session,
    launch_session,
    unregister_session,
)
from app.services.meeting_assistant import get_active_assistant, launch_assistant
from app.services.meeting_bot import get_bot_provider
from app.services.meeting_bot.base import TranscriptSegment
from app.services.stt import get_stt

_logger = logging.getLogger(__name__)
_settings = get_settings()

router = APIRouter()

# ── WebSocket connection manager ──────────────────────────────────────────

class ConnectionManager:
    """Tracks active WebSocket connections per meeting."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, meeting_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(meeting_id, set()).add(ws)
        _logger.info("WS connected for meeting %s (total=%d)", meeting_id, len(self._connections[meeting_id]))

    def disconnect(self, meeting_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(meeting_id, set())
        conns.discard(ws)
        _logger.info("WS disconnected for meeting %s (remaining=%d)", meeting_id, len(conns))

    async def broadcast(self, meeting_id: str, data: dict[str, Any]) -> None:
        """Send a message to all WebSocket clients watching this meeting."""
        conns = self._connections.get(meeting_id, set())
        if not conns:
            return
        dead: set[WebSocket] = set()
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            conns.discard(ws)


_manager = ConnectionManager()


# ── WebSocket endpoint ─────────────────────────────────────────────────────

@router.websocket("/ws/meetings/{meeting_id}")
async def meeting_websocket(meeting_id: str, websocket: WebSocket) -> None:
    """
    Real-time WebSocket endpoint.
    Clients connect here and receive all proxy / transcript / bot events.
    Also bridges Redis pub/sub so events published from background tasks
    reach all connected browsers.
    """
    await _manager.connect(meeting_id, websocket)

    # Subscribe to Redis channel for this meeting
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"meeting:{meeting_id}")

    async def _redis_reader() -> None:
        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue
            try:
                data = json.loads(msg["data"])
                await _manager.broadcast(meeting_id, data)
            except Exception:
                pass

    redis_task = asyncio.create_task(_redis_reader())

    try:
        # Keep connection alive; handle client-to-server messages (e.g. audio chunks)
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Handle audio chunk upload for real-time STT
            if msg.get("type") == "audio_chunk":
                audio_b64 = msg.get("data", "")
                if audio_b64:
                    session = get_active_session(meeting_id)
                    if session:
                        seg = TranscriptSegment(
                            speaker=msg.get("speaker", "User"),
                            text="[audio chunk received]",
                            timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                            is_final=False,
                        )
                        await session.ingest_transcript_segment(seg)

    except WebSocketDisconnect:
        pass
    finally:
        redis_task.cancel()
        await pubsub.unsubscribe(f"meeting:{meeting_id}")
        _manager.disconnect(meeting_id, websocket)


# ── Recall.ai webhook receiver ─────────────────────────────────────────────

@router.post("/webhooks/recall/{meeting_id}", include_in_schema=False)
async def recall_webhook(
    meeting_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Receive real-time events from Recall.ai.
    Recall.ai sends POSTs for: bot.joining_call, bot.in_call_recording,
    transcript.partial, transcript.final, bot.call_ended, etc.
    """
    event = payload.get("event", "")
    data = payload.get("data", {})

    _logger.debug("Recall webhook [%s] meeting=%s", event, meeting_id)

    if "transcript" in event:
        # Real-time transcript segment
        text = data.get("text", "").strip()
        speaker = data.get("speaker", "Unknown")
        is_final = "final" in event

        if text:
            segment = TranscriptSegment(
                speaker=speaker,
                text=text,
                timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
                is_final=is_final,
            )

            # Push to whichever agent is live for this meeting (proxy or assistant)
            session = get_active_session(meeting_id)
            if session:
                await session.ingest_transcript_segment(segment)
            assistant = get_active_assistant(meeting_id)
            if assistant:
                await assistant.ingest_transcript_segment(segment)

            # Broadcast raw transcript to WebSocket clients
            await _manager.broadcast(meeting_id, {
                "type": "transcript",
                "speaker": speaker,
                "text": text,
                "is_final": is_final,
            })

    elif event in {"bot.in_call_recording", "bot.in_call_not_recording"}:
        # Update bot status in DB
        bot_result = await db.execute(
            select(MeetingBot).where(MeetingBot.meeting_id == meeting_id).order_by(MeetingBot.created_at.desc())
        )
        db_bot = bot_result.scalar_one_or_none()
        if db_bot:
            db_bot.status = BotStatus.IN_MEETING
            db_bot.joined_at = datetime.now(timezone.utc)
            await db.commit()

        await _manager.broadcast(meeting_id, {
            "type": "bot_status",
            "status": BotStatus.IN_MEETING,
            "text": "Bot is now recording in the meeting",
        })

    elif event == "bot.call_ended":
        bot_result = await db.execute(
            select(MeetingBot).where(MeetingBot.meeting_id == meeting_id).order_by(MeetingBot.created_at.desc())
        )
        db_bot = bot_result.scalar_one_or_none()
        if db_bot:
            db_bot.status = BotStatus.DONE
            db_bot.left_at = datetime.now(timezone.utc)
            await db.commit()

        await _manager.broadcast(meeting_id, {
            "type": "bot_status",
            "status": BotStatus.DONE,
            "text": "Meeting has ended",
        })

    return Response(status_code=200)


# ── Bot management endpoints ───────────────────────────────────────────────

class JoinMeetingRequest(BaseModel):
    meeting_url: str
    simulate: bool = False  # if true, use simulation mode (no real bot)


@router.post("/workspaces/{workspace_id}/meetings/{meeting_id}/bot/join")
async def join_meeting(
    workspace_id: str,
    meeting_id: str,
    body: JoinMeetingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Deploy a bot to join a meeting on behalf of the user.
    Also starts the live proxy session which drives the AI question flow.
    """
    # Load meeting
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.proxy_consent_given:
        raise HTTPException(
            status_code=400,
            detail="Proxy consent must be given before joining on behalf of user",
        )

    # Check RBAC
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)

    # Check for existing active bot
    existing = await db.execute(
        select(MeetingBot).where(
            MeetingBot.meeting_id == meeting_id,
            MeetingBot.status.in_([BotStatus.CREATED, BotStatus.JOINING, BotStatus.IN_MEETING]),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A bot session is already active for this meeting")

    # Load approved questions
    q_result = await db.execute(
        select(Question).where(
            Question.meeting_id == meeting_id,
            Question.proxy_allowed == True,  # noqa: E712
            Question.status == QuestionStatus.PENDING,
        )
    )
    questions = list(q_result.scalars().all())

    # Launch the live proxy session in the background (it owns its own DB session and
    # sets meeting_url / IN_PROGRESS status itself). Events stream over the WebSocket.
    await launch_session(
        meeting_id=meeting_id,
        workspace_id=workspace_id,
        user_name=current_user.full_name or current_user.email,
        meeting_url=body.meeting_url,
        simulate=body.simulate,
    )

    return {
        "status": "started",
        "meeting_id": meeting_id,
        "simulated": body.simulate,
        "questions_queued": len(questions),
        "message": "Live proxy session started. Connect to WebSocket /api/ws/meetings/{meeting_id} for real-time events.",
    }


@router.get("/workspaces/{workspace_id}/meetings/{meeting_id}/bot/status")
async def get_bot_status(
    workspace_id: str,
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the current status of the meeting bot."""
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.VIEWER)
    result = await db.execute(
        select(MeetingBot)
        .where(MeetingBot.meeting_id == meeting_id)
        .order_by(MeetingBot.created_at.desc())
    )
    db_bot = result.scalar_one_or_none()

    if not db_bot:
        return {"status": "no_bot", "meeting_id": meeting_id}

    live_status: dict[str, Any] = {
        "bot_db_id": db_bot.id,
        "external_bot_id": db_bot.external_bot_id,
        "provider": db_bot.provider,
        "status": db_bot.status,
        "meeting_url": db_bot.meeting_url,
        "joined_at": db_bot.joined_at.isoformat() if db_bot.joined_at else None,
        "left_at": db_bot.left_at.isoformat() if db_bot.left_at else None,
        "session_active": get_active_session(meeting_id) is not None,
    }

    # Try live status from provider
    if db_bot.external_bot_id and db_bot.provider == "recall":
        try:
            bot_provider = get_bot_provider()
            bot_info = await bot_provider.get_bot_status(db_bot.external_bot_id)
            live_status["live_status"] = bot_info.status
        except Exception as exc:
            live_status["live_status_error"] = str(exc)

    return live_status


@router.post("/workspaces/{workspace_id}/meetings/{meeting_id}/bot/leave")
async def leave_meeting(
    workspace_id: str,
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove the bot from the meeting and end the session."""
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)
    result = await db.execute(
        select(MeetingBot)
        .where(MeetingBot.meeting_id == meeting_id)
        .order_by(MeetingBot.created_at.desc())
    )
    db_bot = result.scalar_one_or_none()

    if db_bot and db_bot.external_bot_id:
        try:
            bot_provider = get_bot_provider()
            await bot_provider.leave_meeting(db_bot.external_bot_id)
        except Exception:
            pass
        db_bot.status = BotStatus.DONE
        db_bot.left_at = datetime.now(timezone.utc)

    unregister_session(meeting_id)
    await db.commit()

    await _manager.broadcast(meeting_id, {
        "type": "bot_status",
        "status": "done",
        "text": "Bot has left the meeting",
    })

    return {"status": "left", "meeting_id": meeting_id}


# ── Meeting Assistant agent ────────────────────────────────────────────────

class AssistantStartRequest(BaseModel):
    mode: str = "assistant"        # "assistant" (listen + reply) | "recorder" (silent)
    meeting_url: str = ""
    simulate: bool = False         # real bot by default — no simulation
    assistant_name: str = "AmMeeting"


def detect_platform(url: str) -> str:
    u = (url or "").lower()
    if "meet.google.com" in u:
        return "google_meet"
    if "zoom.us" in u or "zoom.com" in u:
        return "zoom"
    if "teams.microsoft" in u or "teams.live.com" in u:
        return "teams"
    if "jit.si" in u or "jitsi" in u or "8x8.vc" in u or "ffmuc" in u:
        return "jitsi"
    return "other"


@router.post("/workspaces/{workspace_id}/meetings/{meeting_id}/assistant/start")
async def start_assistant(
    workspace_id: str,
    meeting_id: str,
    body: AssistantStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Send the meeting-assistant agent to attend, listen, and (in assistant mode) reply.
    Connect to the WebSocket /api/ws/meetings/{meeting_id} for live events."""
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)

    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not meeting.proxy_consent_given:
        raise HTTPException(
            status_code=400,
            detail="Consent must be given before the assistant can attend/record on your behalf.",
        )
    if body.mode not in ("assistant", "recorder"):
        raise HTTPException(status_code=400, detail="mode must be 'assistant' or 'recorder'")
    if get_active_assistant(meeting_id):
        raise HTTPException(status_code=409, detail="An assistant is already active for this meeting")

    await launch_assistant(
        meeting_id=meeting_id,
        workspace_id=workspace_id,
        owner_name=current_user.full_name or current_user.email,
        mode=body.mode,
        assistant_name=body.assistant_name or "AmMeeting",
        meeting_url=body.meeting_url or None,
        simulate=body.simulate,
    )
    return {
        "status": "started",
        "mode": body.mode,
        "meeting_id": meeting_id,
        "message": "Assistant agent started. Connect to WebSocket /api/ws/meetings/{meeting_id} for live events.",
    }


# ── One-shot test join: paste a link + "now" or a time → real bot attends ──────

class TestJoinRequest(BaseModel):
    meeting_url: str
    when: str = "now"          # "now" or an ISO-8601 datetime
    mode: str = "recorder"     # "recorder" (silent) | "assistant" (listen + reply)
    title: str | None = None


@router.post("/workspaces/{workspace_id}/meetings/test-join")
async def test_join(
    workspace_id: str,
    body: TestJoinRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a meeting from a raw link and send the REAL bot to attend — now, or at a
    scheduled time (handed to the auto-join scheduler). No simulation."""
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)

    # Real bot only — never silently fall back to the mock provider.
    if _settings.bot_provider == "mock":
        raise HTTPException(
            status_code=503,
            detail="Live bot is not configured. Start the bot-worker and set BOT_PROVIDER=browser (or recall).",
        )

    url = body.meeting_url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Provide a full meeting URL (https://…).")
    if body.mode not in ("recorder", "assistant"):
        raise HTTPException(status_code=400, detail="mode must be 'recorder' or 'assistant'")

    platform = detect_platform(url)
    now = datetime.now(timezone.utc)
    if body.when == "now":
        scheduled_at, join_now = now, True
    else:
        try:
            scheduled_at = datetime.fromisoformat(body.when.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="`when` must be 'now' or an ISO datetime.")
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        join_now = scheduled_at <= now + timedelta(minutes=1)

    meeting = Meeting(
        workspace_id=workspace_id,
        title=body.title or f"Test join — {platform}",
        mode=MeetingMode.PROXY,
        status=MeetingStatus.READY,
        meeting_url=url,
        scheduled_at=scheduled_at,
        proxy_consent_given=True,
        auto_join_enabled=not join_now,  # future → the running scheduler dispatches it
    )
    db.add(meeting)
    await db.flush()
    meeting_id = meeting.id
    db.add(AuditLog(
        user_id=current_user.id, workspace_id=workspace_id, action="meeting.test_join",
        resource_type="meeting", resource_id=meeting_id,
        detail=f"platform={platform} when={body.when} mode={body.mode}",
    ))
    await db.commit()

    note = (
        "Google Meet blocks bots that aren't signed in — the bot will reach the lobby and be "
        "denied unless you run the one-time google-login. Watch the live status for the exact result."
        if platform == "google_meet" else None
    )

    if join_now:
        await launch_assistant(
            meeting_id=meeting_id,
            workspace_id=workspace_id,
            owner_name=current_user.full_name or current_user.email,
            mode=body.mode,
            assistant_name="AmMeeting",
            meeting_url=url,
            simulate=False,
        )
        return {
            "meeting_id": meeting_id,
            "platform": platform,
            "joining": True,
            "websocket": f"/api/ws/meetings/{meeting_id}",
            "note": note,
            "message": f"Bot is joining the {platform} meeting now — watch live status below.",
        }

    return {
        "meeting_id": meeting_id,
        "platform": platform,
        "joining": False,
        "scheduled_at": scheduled_at.isoformat(),
        "websocket": f"/api/ws/meetings/{meeting_id}",
        "note": note,
        "message": f"Scheduled — the bot will auto-join at {scheduled_at.isoformat()}.",
    }


@router.post("/workspaces/{workspace_id}/meetings/{meeting_id}/assistant/stop")
async def stop_assistant(
    workspace_id: str,
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Tell the assistant to wrap up, summarize, and leave the meeting."""
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)
    agent = get_active_assistant(meeting_id)
    if not agent:
        return {"status": "not_running", "meeting_id": meeting_id}
    agent.stop()
    return {"status": "stopping", "meeting_id": meeting_id}


# ── Audio upload → Whisper transcription ──────────────────────────────────

@router.post("/workspaces/{workspace_id}/meetings/{meeting_id}/transcribe-audio")
async def transcribe_audio(
    workspace_id: str,
    meeting_id: str,
    audio_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Upload an audio file and transcribe it using the configured STT provider
    (Whisper or mock). Returns the transcript text.
    """
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.MEMBER)
    # Validate file size (25 MB limit)
    MAX_SIZE = 25 * 1024 * 1024
    audio_bytes = await audio_file.read()
    if len(audio_bytes) > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large ({len(audio_bytes)//1024//1024} MB). Maximum is 25 MB.",
        )

    stt = get_stt()
    try:
        transcript = await stt.transcribe_bytes(audio_bytes, filename=audio_file.filename or "audio.wav")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc

    # Broadcast transcript to WebSocket clients
    await _manager.broadcast(meeting_id, {
        "type": "transcript",
        "speaker": "Uploaded Audio",
        "text": transcript,
        "is_final": True,
        "source": "upload",
    })

    return {
        "transcript": transcript,
        "chars": len(transcript),
        "filename": audio_file.filename,
    }


# ── TTS synthesis endpoint ─────────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str
    voice: str = "nova"


@router.post("/workspaces/{workspace_id}/tts")
async def synthesize_tts(
    workspace_id: str,
    body: TTSRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Convert text to speech and return MP3 audio.
    The frontend can play this directly in the browser.
    """
    await require_workspace_role(workspace_id, current_user, db, WorkspaceRole.VIEWER)
    from app.services.tts import get_tts
    tts = get_tts()
    try:
        audio_bytes = await tts.synthesize(body.text[:500])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TTS failed: {exc}") from exc

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=speech.mp3",
            "Content-Length": str(len(audio_bytes)),
        },
    )
