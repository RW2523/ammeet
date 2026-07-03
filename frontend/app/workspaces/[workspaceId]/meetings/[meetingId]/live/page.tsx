"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { meetingApi, liveSessionApi, questionApi } from "@/lib/api-client";
import type { ProxyEvent, Question, TranscriptSegment } from "@/lib/types";
import { cn } from "@/lib/utils";

// ── Status badge colours ────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  created: "bg-yellow-100 text-yellow-700",
  joining: "bg-blue-100 text-blue-700",
  in_meeting: "bg-green-100 text-green-700",
  leaving: "bg-orange-100 text-orange-700",
  done: "bg-gray-100 text-gray-600",
  error: "bg-red-100 text-red-700",
  no_bot: "bg-gray-100 text-gray-500",
};

const EVENT_ICONS: Record<string, string> = {
  disclosure: "📢",
  asking: "❓",
  answered: "✅",
  escalation: "🔴",
  clarifying: "🔍",
  info: "ℹ️",
  session_complete: "🎉",
  bot_status: "🤖",
  transcript: "💬",
  tts_audio: "🔊",
  error: "❌",
};

// ─────────────────────────────────────────────────────────────────────────────
export default function LiveMeetingRoomPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const meetingId = params.meetingId as string;

  // ── State ─────────────────────────────────────────────────────────────────
  const [meetingUrl, setMeetingUrl] = useState("");
  const [simulate, setSimulate] = useState(false);
  const [botStatus, setBotStatus] = useState<string>("no_bot");
  const [sessionActive, setSessionActive] = useState(false);
  const [events, setEvents] = useState<Array<ProxyEvent & { id: number; ts: string }>>([]);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [audioQueue, setAudioQueue] = useState<string[]>([]);
  const [playingAudio, setPlayingAudio] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);
  const eventIdRef = useRef(0);
  const eventListRef = useRef<HTMLDivElement>(null);

  // ── Data fetching ─────────────────────────────────────────────────────────
  const { data: meeting } = useQuery({
    queryKey: ["meeting", workspaceId, meetingId],
    queryFn: () => meetingApi.get(workspaceId, meetingId),
  });

  const { data: questions = [] } = useQuery({
    queryKey: ["questions", workspaceId, meetingId],
    queryFn: () => questionApi.list(workspaceId, meetingId),
  });

  const { data: botInfo, refetch: refetchBot } = useQuery({
    queryKey: ["bot-status", workspaceId, meetingId],
    queryFn: () => liveSessionApi.getBotStatus(workspaceId, meetingId),
    refetchInterval: sessionActive ? 5000 : false,
  });

  // Reflect the fetched bot status in the UI (so a reload shows the real state).
  useEffect(() => {
    if (!botInfo) return;
    const s = (botInfo as { live_status?: string; status?: string }).live_status
      ?? (botInfo as { status?: string }).status;
    if (s) setBotStatus(s);
    if ((botInfo as { session_active?: boolean }).session_active) setSessionActive(true);
  }, [botInfo]);

  // ── WebSocket setup ───────────────────────────────────────────────────────
  const addEvent = useCallback((event: ProxyEvent) => {
    const id = ++eventIdRef.current;
    const ts = new Date().toLocaleTimeString();
    setEvents((prev) => [...prev.slice(-200), { ...event, id, ts }]);
  }, []);

  // Declared before the WebSocket effect below so the effect's onmessage closure
  // does not reference it before initialization (react-hooks/immutability).
  const handleIncomingEvent = useCallback((event: ProxyEvent) => {
    addEvent(event);

    if (event.type === "bot_status") {
      setBotStatus(event.status || "no_bot");
      if (event.status === "in_meeting") {
        toast.success("Bot is now live in the meeting");
      }
    }

    if (event.type === "transcript" && event.text && event.speaker) {
      setTranscript((prev) => [
        ...prev.slice(-100),
        {
          speaker: event.speaker!,
          text: event.text!,
          is_final: event.is_final ?? true,
          source: event.source,
        },
      ]);
    }

    if (event.type === "tts_audio" && event.audio_b64) {
      setAudioQueue((prev) => [...prev, event.audio_b64!]);
    }

    if (event.type === "session_complete") {
      setSessionActive(false);
      setBotStatus("done");
      toast.success("Proxy session complete!");
    }

    if (event.type === "error") {
      toast.error(event.text || "Session error");
    }
  }, [addEvent]);

  useEffect(() => {
    if (!meetingId) return;

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const token = localStorage.getItem("access_token") ?? "";
    const wsUrl = apiBase.replace(/^http/, "ws") + `/api/ws/meetings/${meetingId}?token=${token}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected for meeting", meetingId);
    };

    ws.onmessage = (e) => {
      try {
        const event: ProxyEvent = JSON.parse(e.data);
        handleIncomingEvent(event);
      } catch {
        // ignore
      }
    };

    ws.onerror = (e) => console.error("WS error:", e);
    ws.onclose = () => console.log("WS disconnected");

    return () => {
      ws.close();
    };
  }, [meetingId, handleIncomingEvent]);

  // Auto-scroll event list
  useEffect(() => {
    if (eventListRef.current) {
      eventListRef.current.scrollTop = eventListRef.current.scrollHeight;
    }
  }, [events]);

  // ── Audio playback queue ──────────────────────────────────────────────────
  // Dequeue-and-play legitimately updates state inside the effect; it is guarded
  // by `playingAudio` so it cannot loop, and `playingAudio` drives the UI badge.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!playingAudio && audioQueue.length > 0) {
      const [next, ...rest] = audioQueue;
      setAudioQueue(rest);
      setPlayingAudio(true);

      const audio = new Audio(`data:audio/mp3;base64,${next}`);
      audioRef.current = audio;
      audio.onended = () => setPlayingAudio(false);
      audio.onerror = () => setPlayingAudio(false);
      audio.play().catch(() => setPlayingAudio(false));
    }
  }, [audioQueue, playingAudio]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // ── Mutations ─────────────────────────────────────────────────────────────
  const joinMutation = useMutation({
    mutationFn: () =>
      liveSessionApi.joinMeeting(workspaceId, meetingId, {
        meeting_url: meetingUrl || "https://zoom.us/j/demo",
        simulate,
      }),
    onSuccess: (data) => {
      setSessionActive(true);
      setBotStatus("joining");
      toast.success(`Session started — ${data.questions_queued} questions queued`);
      refetchBot();
    },
    onError: (err: Error) => toast.error(err.message || "Failed to start session"),
  });

  const leaveMutation = useMutation({
    mutationFn: () => liveSessionApi.leaveMeeting(workspaceId, meetingId),
    onSuccess: () => {
      setSessionActive(false);
      setBotStatus("done");
      toast.info("Bot has left the meeting");
      refetchBot();
    },
  });

  // ── Audio recording (browser mic → STT upload) ────────────────────────────
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = recorder;
      recordingChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordingChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const blob = new Blob(recordingChunksRef.current, { type: "audio/webm" });
        const file = new File([blob], "recording.webm", { type: "audio/webm" });
        setUploadProgress("Transcribing audio…");
        try {
          const result = await liveSessionApi.transcribeAudio(workspaceId, meetingId, file);
          toast.success(`Transcribed: "${result.transcript.slice(0, 60)}…"`);
        } catch (err) {
          toast.error("Transcription failed");
        } finally {
          setUploadProgress(null);
        }
        stream.getTracks().forEach((t) => t.stop());
      };

      recorder.start(1000);
      setIsRecording(true);
      toast.info("Recording… click Stop when done");
    } catch {
      toast.error("Microphone access denied");
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  };

  // ── Helpers ───────────────────────────────────────────────────────────────
  const approvedQuestions = questions.filter((q: Question) => q.proxy_allowed);
  const answeredCount = questions.filter((q: Question) => q.status === "answered").length;
  const escalatedCount = questions.filter((q: Question) => q.status === "escalated").length;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 font-mono">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <button
            onClick={() => router.back()}
            className="text-gray-400 hover:text-white text-sm mb-1 flex items-center gap-1"
          >
            ← Back
          </button>
          <h1 className="text-xl font-bold text-white">
            🤖 Live Meeting Room
          </h1>
          {meeting && (
            <p className="text-gray-400 text-sm">{meeting.title}</p>
          )}
        </div>

        {/* Bot status badge */}
        <div className="flex flex-col items-end gap-2">
          <span
            className={cn(
              "px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wide",
              STATUS_COLORS[botStatus] || "bg-gray-700 text-gray-300"
            )}
          >
            {botStatus.replace(/_/g, " ")}
          </span>
          {playingAudio && (
            <span className="text-xs text-green-400 animate-pulse">🔊 Speaking…</span>
          )}
          {isRecording && (
            <span className="text-xs text-red-400 animate-pulse">🎙 Recording…</span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* ── Left: Controls + Questions ──────────────────────────────────── */}
        <div className="space-y-4">
          {/* Join controls */}
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-700">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Bot Controls</h2>

            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 mb-1 block">
                  Meeting URL (Zoom / Meet / Teams)
                </label>
                <input
                  type="url"
                  value={meetingUrl}
                  onChange={(e) => setMeetingUrl(e.target.value)}
                  placeholder="https://zoom.us/j/123456789"
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                  disabled={sessionActive}
                />
              </div>

              <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={simulate}
                  onChange={(e) => setSimulate(e.target.checked)}
                  disabled={sessionActive}
                  className="rounded"
                />
                Simulation mode (no real bot — demo with AI answers)
              </label>

              {!sessionActive ? (
                <button
                  onClick={() => joinMutation.mutate()}
                  disabled={joinMutation.isPending || !meeting?.proxy_consent_given}
                  className="w-full bg-green-600 hover:bg-green-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg py-2 text-sm font-semibold transition"
                >
                  {joinMutation.isPending ? "Joining…" : "🚀 Join Meeting"}
                </button>
              ) : (
                <button
                  onClick={() => leaveMutation.mutate()}
                  disabled={leaveMutation.isPending}
                  className="w-full bg-red-700 hover:bg-red-600 text-white rounded-lg py-2 text-sm font-semibold transition"
                >
                  {leaveMutation.isPending ? "Leaving…" : "🛑 Leave Meeting"}
                </button>
              )}

              {!meeting?.proxy_consent_given && (
                <p className="text-xs text-amber-400">
                  ⚠️ Proxy consent must be enabled for this meeting first.
                </p>
              )}
            </div>
          </div>

          {/* Mic recording */}
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-700">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Upload Audio / Record</h2>
            <div className="space-y-2">
              {!isRecording ? (
                <button
                  onClick={startRecording}
                  className="w-full bg-blue-700 hover:bg-blue-600 text-white rounded-lg py-2 text-sm font-semibold transition"
                >
                  🎙 Start Recording
                </button>
              ) : (
                <button
                  onClick={stopRecording}
                  className="w-full bg-red-700 hover:bg-red-600 text-white rounded-lg py-2 text-sm font-semibold animate-pulse transition"
                >
                  ⏹ Stop & Transcribe
                </button>
              )}

              <label className="w-full flex items-center justify-center gap-2 bg-gray-700 hover:bg-gray-600 cursor-pointer text-white rounded-lg py-2 text-sm font-semibold transition">
                📁 Upload Audio File
                <input
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    setUploadProgress("Transcribing…");
                    try {
                      const result = await liveSessionApi.transcribeAudio(workspaceId, meetingId, file);
                      toast.success(`Transcribed ${result.chars} chars`);
                    } catch {
                      toast.error("Transcription failed");
                    } finally {
                      setUploadProgress(null);
                      e.target.value = "";
                    }
                  }}
                />
              </label>

              {uploadProgress && (
                <p className="text-xs text-blue-400 animate-pulse text-center">{uploadProgress}</p>
              )}
            </div>
          </div>

          {/* Question summary */}
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-700">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Questions</h2>
            <div className="grid grid-cols-3 gap-2 text-center mb-3">
              <div className="bg-gray-800 rounded-lg p-2">
                <div className="text-lg font-bold text-blue-400">{approvedQuestions.length}</div>
                <div className="text-xs text-gray-500">Approved</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-2">
                <div className="text-lg font-bold text-green-400">{answeredCount}</div>
                <div className="text-xs text-gray-500">Answered</div>
              </div>
              <div className="bg-gray-800 rounded-lg p-2">
                <div className="text-lg font-bold text-red-400">{escalatedCount}</div>
                <div className="text-xs text-gray-500">Escalated</div>
              </div>
            </div>

            <div className="space-y-1 max-h-48 overflow-y-auto">
              {questions.map((q: Question) => (
                <div
                  key={q.id}
                  className={cn(
                    "text-xs px-2 py-1 rounded flex items-start gap-1",
                    q.status === "answered" && "bg-green-900/30 text-green-300",
                    q.status === "escalated" && "bg-red-900/30 text-red-300",
                    q.status === "asked" && "bg-blue-900/30 text-blue-300 animate-pulse",
                    q.status === "pending" && "bg-gray-800 text-gray-400",
                    q.status === "skipped" && "bg-gray-800 text-gray-500 line-through",
                  )}
                >
                  <span>
                    {q.status === "answered" ? "✅" :
                     q.status === "escalated" ? "🔴" :
                     q.status === "asked" ? "❓" : "•"}
                  </span>
                  <span className="truncate">{q.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Center: Live transcript ───────────────────────────────────────── */}
        <div className="bg-gray-900 rounded-xl border border-gray-700 flex flex-col">
          <div className="p-3 border-b border-gray-700 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-300">💬 Live Transcript</h2>
            <span className="text-xs text-gray-500">{transcript.length} segments</span>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-2 min-h-[400px] max-h-[600px]">
            {transcript.length === 0 ? (
              <p className="text-gray-600 text-sm text-center mt-8">
                Transcript will appear here when the meeting starts.
              </p>
            ) : (
              transcript.map((seg, i) => (
                <div key={i} className="text-sm">
                  <span className="text-blue-400 font-semibold mr-2">{seg.speaker}:</span>
                  <span className={cn("text-gray-200", !seg.is_final && "text-gray-400 italic")}>
                    {seg.text}
                    {!seg.is_final && <span className="text-gray-500"> …</span>}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Right: Event log ──────────────────────────────────────────────── */}
        <div className="bg-gray-900 rounded-xl border border-gray-700 flex flex-col">
          <div className="p-3 border-b border-gray-700 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-300">🤖 Proxy Events</h2>
            <div className="flex gap-2">
              {events.length > 0 && (
                <button
                  onClick={() => setEvents([])}
                  className="text-xs text-gray-500 hover:text-gray-300"
                >
                  Clear
                </button>
              )}
              <span className="text-xs text-gray-500">{events.length} events</span>
            </div>
          </div>

          <div
            ref={eventListRef}
            className="flex-1 overflow-y-auto p-3 space-y-2 min-h-[400px] max-h-[600px]"
          >
            {events.length === 0 ? (
              <p className="text-gray-600 text-sm text-center mt-8">
                AI proxy events will appear here once the session starts.
              </p>
            ) : (
              events.map((event) => (
                <div
                  key={event.id}
                  className={cn(
                    "text-xs rounded-lg p-2 border-l-2",
                    event.type === "disclosure" && "border-blue-500 bg-blue-900/20",
                    event.type === "asking" && "border-yellow-500 bg-yellow-900/20",
                    event.type === "answered" && "border-green-500 bg-green-900/20",
                    event.type === "escalation" && "border-red-500 bg-red-900/20",
                    event.type === "clarifying" && "border-purple-500 bg-purple-900/20",
                    event.type === "session_complete" && "border-emerald-500 bg-emerald-900/20",
                    event.type === "bot_status" && "border-cyan-500 bg-cyan-900/20",
                    event.type === "tts_audio" && "border-indigo-500 bg-indigo-900/15",
                    event.type === "transcript" && "border-gray-600 bg-gray-800/30",
                    event.type === "error" && "border-red-700 bg-red-900/30",
                    !["disclosure","asking","answered","escalation","clarifying","session_complete","bot_status","tts_audio","transcript","error"].includes(event.type) &&
                      "border-gray-600 bg-gray-800/20",
                  )}
                >
                  <div className="flex items-center gap-1 mb-1 text-gray-400">
                    <span>{EVENT_ICONS[event.type] || "•"}</span>
                    <span className="font-semibold uppercase tracking-wide">
                      {event.type.replace(/_/g, " ")}
                    </span>
                    <span className="ml-auto text-gray-600">{event.ts}</span>
                  </div>

                  {event.text && event.type !== "transcript" && (
                    <p className="text-gray-200 leading-relaxed">{event.text}</p>
                  )}
                  {event.answer && (
                    <p className="text-green-300 mt-1 italic">Answer: {event.answer}</p>
                  )}
                  {event.reason && (
                    <p className="text-red-300 mt-1">Reason: {event.reason}</p>
                  )}
                  {event.type === "tts_audio" && (
                    <p className="text-indigo-300 mt-1 italic text-xs">
                      🔊 &quot;{event.text?.slice(0, 60)}{(event.text?.length ?? 0) > 60 ? "…" : ""}&quot;
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Escalation alert banner */}
      {events.some((e) => e.type === "escalation") && (
        <div className="mt-4 bg-red-900/40 border border-red-600 rounded-xl p-4">
          <h3 className="text-red-400 font-semibold mb-2">🔴 Escalation Required</h3>
          <div className="space-y-1">
            {events
              .filter((e) => e.type === "escalation")
              .map((e) => (
                <p key={e.id} className="text-sm text-red-200">
                  <strong>Q:</strong> {e.text} — <em>{e.reason}</em>
                </p>
              ))}
          </div>
          <p className="text-xs text-red-400 mt-2">
            These items require your direct attention. Please join the meeting or respond to participants directly.
          </p>
        </div>
      )}
    </div>
  );
}
