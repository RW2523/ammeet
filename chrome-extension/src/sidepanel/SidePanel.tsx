"use client";
import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  type ReactNode,
} from "react";
import type {
  AuthState,
  DetectedMeeting,
  WorkspaceInfo,
  MeetingInfo,
  Question,
  ProxyEvent,
  TranscriptLine,
  ExtensionMessage,
  StoredState,
  BotStatus,
  SessionStatus,
} from "../lib/types";
import { ApiClient } from "../lib/api";
import { BrowserSTT } from "../lib/stt";
import { BrowserTTS } from "../lib/tts";
import { WSManager } from "../lib/websocket";
import { getStoredState, getBackendUrl, onStorageChange } from "../lib/store";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function sendSW(msg: ExtensionMessage): Promise<ExtensionMessage | null> {
  return chrome.runtime.sendMessage(msg).catch(() => null);
}

function clsx(...args: (string | boolean | undefined | null)[]): string {
  return args.filter(Boolean).join(" ");
}

// ─── Status colours ───────────────────────────────────────────────────────────
const STATUS_DOT: Record<string, string> = {
  idle: "bg-gray-500",
  joining: "bg-yellow-400 animate-pulse",
  in_meeting: "bg-green-400 animate-pulse",
  done: "bg-gray-500",
  error: "bg-red-500",
  inactive: "bg-gray-600",
  starting: "bg-blue-400 animate-pulse",
  active: "bg-green-400 animate-pulse",
  ended: "bg-gray-500",
  connecting: "bg-yellow-400 animate-pulse",
  connected: "bg-green-400",
  disconnected: "bg-gray-500",
};

const EVENT_COLORS: Record<string, string> = {
  disclosure: "border-blue-500/60 bg-blue-900/20",
  asking: "border-yellow-500/60 bg-yellow-900/20",
  answered: "border-green-500/60 bg-green-900/20",
  escalation: "border-red-500/60 bg-red-900/25",
  clarifying: "border-purple-500/60 bg-purple-900/20",
  session_complete: "border-emerald-500/60 bg-emerald-900/20",
  bot_status: "border-cyan-500/60 bg-cyan-900/15",
  tts_audio: "border-indigo-500/50 bg-indigo-900/15",
  info: "border-gray-600 bg-gray-800/20",
  error: "border-red-700 bg-red-900/30",
};

const EVENT_ICONS: Record<string, string> = {
  disclosure: "📢",
  asking: "❓",
  answered: "✅",
  escalation: "🔴",
  clarifying: "🔍",
  session_complete: "🎉",
  bot_status: "🤖",
  tts_audio: "🔊",
  info: "ℹ️",
  error: "❌",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function Dot({ status }: { status: string }) {
  return (
    <span
      className={clsx(
        "inline-block w-2 h-2 rounded-full flex-shrink-0",
        STATUS_DOT[status] ?? "bg-gray-500"
      )}
    />
  );
}

function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{title}</span>
        {action}
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}

function Btn({
  onClick,
  disabled,
  variant = "default",
  className,
  title,
  children,
}: {
  onClick?: () => void;
  disabled?: boolean;
  variant?: "default" | "green" | "red" | "outline" | "ghost";
  className?: string;
  title?: string;
  children: ReactNode;
}) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:opacity-40 disabled:pointer-events-none";
  const variants = {
    default: "bg-blue-600 hover:bg-blue-500 text-white",
    green: "bg-green-700 hover:bg-green-600 text-white",
    red: "bg-red-700 hover:bg-red-600 text-white",
    outline: "border border-gray-600 hover:border-gray-400 text-gray-300 hover:text-white",
    ghost: "text-gray-400 hover:text-white hover:bg-gray-800",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={clsx(base, variants[variant], className)}
    >
      {children}
    </button>
  );
}

// ─── Login Screen ─────────────────────────────────────────────────────────────

function LoginScreen({
  onLogin,
}: {
  onLogin: (auth: AuthState) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [backendUrl, setBackendUrl] = useState("http://localhost:8000");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getBackendUrl().then(setBackendUrl);
  }, []);

  const handleLogin = async () => {
    if (!email || !password) return;
    setLoading(true);
    setError("");
    try {
      const resp = await sendSW({ type: "LOGIN", email, password });
      if (resp?.type === "AUTH_STATE_CHANGED") {
        onLogin(resp.auth);
      } else if (resp?.type === "ERROR") {
        setError(resp.message);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-6 bg-gray-950">
      <div className="w-full max-w-xs space-y-6">
        <div className="text-center">
          <div className="text-3xl mb-2">🤖</div>
          <h1 className="text-xl font-bold text-white">AmMeeting</h1>
          <p className="text-gray-400 text-xs mt-1">AI Meeting Proxy Assistant</p>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Backend URL</label>
            <input
              value={backendUrl}
              onChange={(e) => setBackendUrl(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="http://localhost:8000"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="you@company.com"
              autoComplete="email"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <p className="text-red-400 text-xs bg-red-900/20 border border-red-800 rounded px-2 py-1">
              {error}
            </p>
          )}

          <button
            onClick={handleLogin}
            disabled={loading || !email || !password}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg py-2.5 text-sm font-semibold transition"
          >
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </div>

        <p className="text-center text-xs text-gray-600">
          Don't have an account?{" "}
          <a
            href={`${backendUrl}/docs`}
            target="_blank"
            rel="noreferrer"
            className="text-blue-400 hover:underline"
          >
            Open backend docs
          </a>
        </p>
      </div>
    </div>
  );
}

// ─── Main Side Panel ──────────────────────────────────────────────────────────

type Tab = "session" | "transcript" | "questions" | "settings";

export default function SidePanel() {
  // ── Core state ─────────────────────────────────────────────────────────────
  const [auth, setAuth] = useState<AuthState>({ accessToken: null, refreshToken: null, user: null });
  const [backendUrl, setBackendUrl] = useState("http://localhost:8000");
  const [tab, setTab] = useState<Tab>("session");

  // ── Meeting state ──────────────────────────────────────────────────────────
  const [detectedMeeting, setDetectedMeeting] = useState<DetectedMeeting | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceInfo[]>([]);
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>("");
  const [meetings, setMeetings] = useState<MeetingInfo[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<string>("");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [simulateMode, setSimulateMode] = useState(false);

  // ── Session / bot state ────────────────────────────────────────────────────
  const [botStatus, setBotStatus] = useState<BotStatus>("idle");
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("inactive");
  const [wsStatus, setWsStatus] = useState("disconnected");
  const [events, setEvents] = useState<Array<ProxyEvent & { id: number; ts: string }>>([]);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [escalations, setEscalations] = useState<string[]>([]);
  const evtIdRef = useRef(0);
  const eventsEndRef = useRef<HTMLDivElement>(null);

  // ── STT / TTS ──────────────────────────────────────────────────────────────
  const sttRef = useRef<BrowserSTT | null>(null);
  const ttsRef = useRef<BrowserTTS | null>(null);
  const wsRef = useRef<WSManager | null>(null);
  const [sttActive, setSttActive] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [partialTranscript, setPartialTranscript] = useState("");

  // ── Recording (mic → backend Whisper) ─────────────────────────────────────
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordChunksRef = useRef<Blob[]>([]);

  // ── Init ───────────────────────────────────────────────────────────────────
  useEffect(() => {
    // Load persisted state
    getStoredState().then((s) => {
      setAuth(s.auth);
      setBackendUrl(s.backendUrl);
      setDetectedMeeting(s.detectedMeeting);
      setBotStatus(s.botStatus as BotStatus);
      setSessionStatus(s.sessionStatus as SessionStatus);
      if (s.currentWorkspaceId) setSelectedWorkspace(s.currentWorkspaceId);
      if (s.currentMeetingId) setSelectedMeeting(s.currentMeetingId);
    });

    // Storage change listener
    const unsub = onStorageChange(
      ["auth", "detectedMeeting", "botStatus", "sessionStatus", "currentWorkspaceId", "currentMeetingId"],
      (changes) => {
        if (changes.auth !== undefined) setAuth(changes.auth as AuthState);
        if (changes.detectedMeeting !== undefined) setDetectedMeeting(changes.detectedMeeting as DetectedMeeting | null);
        if (changes.botStatus !== undefined) setBotStatus(changes.botStatus as BotStatus);
        if (changes.sessionStatus !== undefined) setSessionStatus(changes.sessionStatus as SessionStatus);
        if (changes.currentWorkspaceId !== undefined && changes.currentWorkspaceId)
          setSelectedWorkspace(changes.currentWorkspaceId as string);
        if (changes.currentMeetingId !== undefined && changes.currentMeetingId)
          setSelectedMeeting(changes.currentMeetingId as string);
      }
    );

    // Init STT
    sttRef.current = new BrowserSTT("en-US");
    // Init TTS
    ttsRef.current = new BrowserTTS({ lang: "en-US" });

    // Init WS manager
    wsRef.current = new WSManager({
      onEvent: handleProxyEvent,
      onStatusChange: (s) => setWsStatus(s),
    });

    // Extension message listener
    const msgListener = (msg: ExtensionMessage) => handleExtensionMessage(msg);
    chrome.runtime.onMessage.addListener(msgListener);

    return () => {
      unsub();
      chrome.runtime.onMessage.removeListener(msgListener);
      sttRef.current?.stop();
      wsRef.current?.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Set up STT callbacks once auth is available
  useEffect(() => {
    const stt = sttRef.current;
    if (!stt) return;

    stt.onPartial = (text) => setPartialTranscript(text);

    stt.onFinal = (text) => {
      setPartialTranscript("");
      const line: TranscriptLine = { speaker: "You (mic)", text, is_final: true, ts: Date.now() };
      setTranscript((prev) => [...prev.slice(-150), line]);
      // Forward to backend via WebSocket
      wsRef.current?.send({ type: "transcript_line", text, speaker: "User" });
    };

    stt.onError = (err) => {
      if (err !== "no-speech") {
        addEvent({ type: "error", text: `STT: ${err}` });
      }
    };
  }, []);

  // Auto-scroll events
  useEffect(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  // Load workspaces when authenticated
  useEffect(() => {
    if (auth.accessToken) {
      loadWorkspaces();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.accessToken]);

  // Load meetings when workspace selected
  useEffect(() => {
    if (selectedWorkspace && auth.accessToken) {
      loadMeetings(selectedWorkspace);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWorkspace]);

  // Load questions when meeting selected
  useEffect(() => {
    if (selectedWorkspace && selectedMeeting && auth.accessToken) {
      loadQuestions(selectedWorkspace, selectedMeeting);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMeeting]);

  // Connect WebSocket when session is active
  useEffect(() => {
    if (sessionStatus === "active" && selectedMeeting && auth.accessToken) {
      const api = new ApiClient(backendUrl, auth.accessToken);
      const wsUrl = api.getWebSocketUrl(selectedMeeting);
      wsRef.current?.connect(wsUrl, selectedMeeting);
    } else if (sessionStatus !== "active") {
      wsRef.current?.disconnect();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionStatus, selectedMeeting]);

  // ── Message handlers ───────────────────────────────────────────────────────

  const handleExtensionMessage = useCallback((msg: ExtensionMessage) => {
    switch (msg.type) {
      case "MEETING_DETECTED":
        setDetectedMeeting(msg.meeting);
        if (msg.meeting.url) {
          // Pre-fill meeting URL from detected meeting
        }
        break;
      case "MEETING_ENDED":
        setDetectedMeeting(null);
        break;
      case "AUTH_STATE_CHANGED":
        setAuth(msg.auth);
        break;
      case "SESSION_STARTED":
        setSessionStatus("active");
        setBotStatus("joining");
        addEvent({ type: "info", text: `Session started — ${msg.questionsQueued} questions queued` });
        break;
      case "SESSION_STOPPED":
        setSessionStatus("inactive");
        setBotStatus("idle");
        wsRef.current?.disconnect();
        break;
      case "PROXY_EVENT":
        handleProxyEvent(msg.event);
        break;
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleProxyEvent = useCallback((event: ProxyEvent) => {
    addEvent(event);

    switch (event.type) {
      case "bot_status":
        if (event.status) setBotStatus(event.status as BotStatus);
        break;

      case "transcript":
        if (event.text && event.speaker) {
          setTranscript((prev) => [
            ...prev.slice(-150),
            { speaker: event.speaker!, text: event.text!, is_final: event.is_final ?? true, ts: Date.now() },
          ]);
        }
        break;

      case "tts_audio":
        if (event.audio_b64 && ttsEnabled && ttsRef.current) {
          ttsRef.current.playAudioB64(event.audio_b64).catch(() => {
            // Fallback to browser TTS
            if (event.text && ttsRef.current) {
              ttsRef.current.speak(event.text).catch(() => {});
            }
          });
        } else if (event.text && ttsEnabled && ttsRef.current) {
          ttsRef.current.speak(event.text).catch(() => {});
        }
        break;

      case "escalation":
        setEscalations((prev) => [...prev, event.text ?? event.reason ?? "Unknown escalation"]);
        // Show browser notification
        chrome.notifications?.create({
          type: "basic",
          iconUrl: chrome.runtime.getURL("icons/icon48.png"),
          title: "⚠️ AmMeeting Escalation",
          message: `Human attention needed: "${(event.text ?? "").slice(0, 80)}"`,
          priority: 2,
        });
        break;

      case "session_complete":
        setSessionStatus("ended");
        setBotStatus("done");
        break;
    }

    // Forward relevant events to content script (overlay update)
    chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      if (tab?.id) {
        chrome.tabs.sendMessage(tab.id, { type: "PROXY_EVENT", event } as ExtensionMessage).catch(() => {});
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ttsEnabled]);

  const addEvent = useCallback((event: ProxyEvent) => {
    setEvents((prev) => [
      ...prev.slice(-300),
      { ...event, id: ++evtIdRef.current, ts: new Date().toLocaleTimeString() },
    ]);
  }, []);

  // ── Data loaders ───────────────────────────────────────────────────────────

  const loadWorkspaces = async () => {
    const resp = await sendSW({ type: "GET_WORKSPACES" });
    if (resp?.type === "WORKSPACES_RESULT") {
      setWorkspaces(resp.workspaces);
      if (resp.workspaces.length === 1 && !selectedWorkspace) {
        setSelectedWorkspace(resp.workspaces[0].id);
      }
    }
  };

  const loadMeetings = async (wsId: string) => {
    const resp = await sendSW({ type: "GET_MEETINGS", workspaceId: wsId });
    if (resp?.type === "MEETINGS_RESULT") {
      setMeetings(resp.meetings);
    }
  };

  const loadQuestions = async (wsId: string, mId: string) => {
    const resp = await sendSW({ type: "GET_QUESTIONS", workspaceId: wsId, meetingId: mId });
    if (resp?.type === "QUESTIONS_RESULT") {
      setQuestions(resp.questions);
    }
  };

  // ── Session controls ───────────────────────────────────────────────────────

  const startSession = async () => {
    if (!selectedWorkspace || !selectedMeeting) return;
    setSessionStatus("starting");
    const resp = await sendSW({
      type: "START_SESSION",
      workspaceId: selectedWorkspace,
      meetingId: selectedMeeting,
      meetingUrl: detectedMeeting?.url ?? "https://zoom.us/j/demo",
      simulate: simulateMode,
    });
    if (resp?.type === "ERROR") {
      addEvent({ type: "error", text: resp.message });
      setSessionStatus("inactive");
    }
  };

  const stopSession = async () => {
    if (!selectedWorkspace || !selectedMeeting) return;
    await sendSW({ type: "STOP_SESSION", workspaceId: selectedWorkspace, meetingId: selectedMeeting });
    sttRef.current?.stop();
    setSttActive(false);
    ttsRef.current?.cancel();
  };

  // ── STT controls ───────────────────────────────────────────────────────────

  const toggleSTT = () => {
    const stt = sttRef.current;
    if (!stt) return;
    if (!stt.isSupported) {
      addEvent({ type: "error", text: "Web Speech API not supported in this browser." });
      return;
    }
    if (sttActive) {
      stt.stop();
      setSttActive(false);
    } else {
      stt.start();
      setSttActive(true);
    }
  };

  // ── Recording (upload to Whisper) ──────────────────────────────────────────

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });
      recordChunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) recordChunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        const blob = new Blob(recordChunksRef.current, { type: "audio/webm" });
        if (!selectedWorkspace || !selectedMeeting || !auth.accessToken) return;
        const api = new ApiClient(backendUrl, auth.accessToken);
        try {
          const result = await api.transcribeAudio(selectedWorkspace, selectedMeeting, blob);
          setTranscript((prev) => [
            ...prev,
            { speaker: "Uploaded audio", text: result.transcript, is_final: true, ts: Date.now() },
          ]);
        } catch (e) {
          addEvent({ type: "error", text: `Transcription failed: ${e}` });
        }
        stream.getTracks().forEach((t) => t.stop());
      };
      mr.start(500);
      mediaRecorderRef.current = mr;
      setRecording(true);
    } catch {
      addEvent({ type: "error", text: "Microphone access denied." });
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  };

  // ── Logout ─────────────────────────────────────────────────────────────────

  const logout = () => {
    sendSW({ type: "LOGOUT" });
    setWorkspaces([]);
    setMeetings([]);
    setSelectedWorkspace("");
    setSelectedMeeting("");
    setEvents([]);
    setTranscript([]);
  };

  // ── Not logged in ──────────────────────────────────────────────────────────
  if (!auth.accessToken) {
    return <LoginScreen onLogin={setAuth} />;
  }

  const selectedMeetingInfo = meetings.find((m) => m.id === selectedMeeting);
  const approvedQs = questions.filter((q) => q.proxy_allowed && !q.human_only);
  const answeredQs = questions.filter((q) => q.status === "answered");
  const escalatedQs = questions.filter((q) => q.status === "escalated");

  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 overflow-hidden text-xs">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <span className="text-base">🤖</span>
        <span className="font-bold text-white text-sm">AmMeeting</span>
        <div className="flex items-center gap-1 ml-1">
          <Dot status={wsStatus} />
          <span className="text-gray-500">{wsStatus}</span>
        </div>
        <div className="ml-auto flex items-center gap-1">
          <span className="text-gray-500 text-xs">{auth.user?.email}</span>
          <Btn variant="ghost" onClick={logout}>
            ↩
          </Btn>
        </div>
      </div>

      {/* Detection banner */}
      {detectedMeeting && (
        <div className="px-3 py-1.5 bg-green-900/30 border-b border-green-800/50 flex items-center gap-2 flex-shrink-0">
          <Dot status="active" />
          <span className="text-green-300 font-medium capitalize">{detectedMeeting.platform}</span>
          <span className="text-green-400">meeting detected</span>
          {detectedMeeting.participants.length > 0 && (
            <span className="text-green-600 ml-auto">{detectedMeeting.participants.length} participants</span>
          )}
        </div>
      )}

      {/* Tab bar */}
      <div className="flex border-b border-gray-800 flex-shrink-0 bg-gray-900">
        {(["session", "transcript", "questions", "settings"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "flex-1 py-2 text-xs font-semibold capitalize transition border-b-2",
              tab === t
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-gray-500 hover:text-gray-300"
            )}
          >
            {t === "session"
              ? "🚀 Session"
              : t === "transcript"
              ? "💬 Transcript"
              : t === "questions"
              ? `❓ Questions${questions.length > 0 ? ` (${questions.length})` : ""}`
              : "⚙️ Settings"}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">

        {/* ── SESSION TAB ───────────────────────────────────────────────────── */}
        {tab === "session" && (
          <div className="p-3 space-y-3">
            {/* Meeting selector */}
            <Section title="Meeting Setup">
              <div className="space-y-2">
                <div>
                  <label className="text-gray-500 mb-1 block">Workspace</label>
                  <select
                    value={selectedWorkspace}
                    onChange={(e) => setSelectedWorkspace(e.target.value)}
                    disabled={sessionStatus === "active"}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="">— select workspace —</option>
                    {workspaces.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-gray-500 mb-1 block">Meeting</label>
                  <select
                    value={selectedMeeting}
                    onChange={(e) => setSelectedMeeting(e.target.value)}
                    disabled={!selectedWorkspace || sessionStatus === "active"}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="">— select meeting —</option>
                    {meetings.map((m) => (
                      <option key={m.id} value={m.id} disabled={!m.proxy_consent_given}>
                        {m.title} {!m.proxy_consent_given ? "(no proxy consent)" : ""}
                      </option>
                    ))}
                  </select>
                </div>

                <label className="flex items-center gap-2 text-gray-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={simulateMode}
                    onChange={(e) => setSimulateMode(e.target.checked)}
                    disabled={sessionStatus === "active"}
                    className="rounded"
                  />
                  Simulation mode (AI generates answers)
                </label>
              </div>
            </Section>

            {/* Status bar */}
            <Section
              title="Bot Status"
              action={
                <div className="flex items-center gap-1">
                  <Dot status={botStatus} />
                  <span className="text-gray-400 capitalize">{botStatus.replace(/_/g, " ")}</span>
                </div>
              }
            >
              <div className="grid grid-cols-3 gap-2 text-center mb-2">
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-base font-bold text-blue-400">{approvedQs.length}</div>
                  <div className="text-gray-500">Approved</div>
                </div>
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-base font-bold text-green-400">{answeredQs.length}</div>
                  <div className="text-gray-500">Answered</div>
                </div>
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-base font-bold text-red-400">{escalatedQs.length}</div>
                  <div className="text-gray-500">Escalated</div>
                </div>
              </div>

              {/* Controls */}
              <div className="flex gap-2 flex-wrap">
                {sessionStatus === "inactive" || sessionStatus === "ended" ? (
                  <Btn
                    variant="green"
                    onClick={startSession}
                    disabled={!selectedMeeting || !selectedMeetingInfo?.proxy_consent_given}
                    className="flex-1"
                  >
                    🚀 Start Session
                  </Btn>
                ) : sessionStatus === "starting" ? (
                  <Btn variant="outline" disabled className="flex-1">
                    Starting…
                  </Btn>
                ) : (
                  <Btn variant="red" onClick={stopSession} className="flex-1">
                    🛑 Stop Session
                  </Btn>
                )}

                <Btn
                  variant={sttActive ? "red" : "outline"}
                  onClick={toggleSTT}
                  title={sttActive ? "Stop mic transcription" : "Start mic transcription (Web Speech API)"}
                >
                  {sttActive ? "🎙 Stop STT" : "🎙 Start STT"}
                </Btn>

                <Btn
                  variant={recording ? "red" : "outline"}
                  onClick={recording ? stopRecording : startRecording}
                  title={recording ? "Stop and upload for Whisper transcription" : "Record audio"}
                >
                  {recording ? "⏹ Upload" : "🔴 Record"}
                </Btn>

                <Btn
                  variant="ghost"
                  onClick={() => {
                    setTtsEnabled((v) => !v);
                    if (ttsEnabled) ttsRef.current?.cancel();
                  }}
                  title={ttsEnabled ? "Mute AI voice" : "Unmute AI voice"}
                >
                  {ttsEnabled ? "🔊 TTS On" : "🔇 TTS Off"}
                </Btn>
              </div>

              {!selectedMeetingInfo?.proxy_consent_given && selectedMeeting && (
                <p className="text-amber-400 mt-2">
                  ⚠️ Enable proxy consent for this meeting in the web app first.
                </p>
              )}
            </Section>

            {/* Partial STT indicator */}
            {partialTranscript && (
              <div className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-gray-400 italic">
                🎙 {partialTranscript}
              </div>
            )}

            {/* Escalation alerts */}
            {escalations.length > 0 && (
              <div className="bg-red-900/30 border border-red-700 rounded-xl p-3">
                <div className="font-semibold text-red-400 mb-2">🔴 Escalations — Human Required</div>
                {escalations.map((e, i) => (
                  <p key={i} className="text-red-200 mb-1">
                    • {e}
                  </p>
                ))}
                <Btn
                  variant="ghost"
                  onClick={() => setEscalations([])}
                  className="mt-1 text-red-500"
                >
                  Dismiss all
                </Btn>
              </div>
            )}

            {/* Events log */}
            <Section
              title={`Proxy Events (${events.length})`}
              action={
                events.length > 0 ? (
                  <Btn variant="ghost" onClick={() => setEvents([])}>
                    Clear
                  </Btn>
                ) : undefined
              }
            >
              {events.length === 0 ? (
                <p className="text-gray-600 text-center py-4">
                  Events will appear here once the session starts.
                </p>
              ) : (
                <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
                  {events.map((evt) => (
                    <div
                      key={evt.id}
                      className={clsx(
                        "rounded-lg p-2 border-l-2 text-xs",
                        EVENT_COLORS[evt.type] ?? "border-gray-600 bg-gray-800/20"
                      )}
                    >
                      <div className="flex items-center gap-1 text-gray-400 mb-0.5">
                        <span>{EVENT_ICONS[evt.type] ?? "•"}</span>
                        <span className="font-semibold uppercase tracking-wide text-[10px]">
                          {evt.type.replace(/_/g, " ")}
                        </span>
                        <span className="ml-auto text-gray-600">{evt.ts}</span>
                      </div>
                      {evt.text && evt.type !== "transcript" && (
                        <p className="text-gray-200 leading-relaxed">{evt.text}</p>
                      )}
                      {evt.answer && (
                        <p className="text-green-300 italic mt-0.5">→ {evt.answer}</p>
                      )}
                      {evt.reason && <p className="text-red-300 mt-0.5">Reason: {evt.reason}</p>}
                    </div>
                  ))}
                  <div ref={eventsEndRef} />
                </div>
              )}
            </Section>
          </div>
        )}

        {/* ── TRANSCRIPT TAB ────────────────────────────────────────────────── */}
        {tab === "transcript" && (
          <div className="p-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-gray-400">
                {sttActive ? (
                  <span className="text-green-400 animate-pulse">🎙 Listening…</span>
                ) : (
                  <span className="text-gray-500">Mic off</span>
                )}
              </span>
              <Btn variant={sttActive ? "red" : "outline"} onClick={toggleSTT} className="ml-auto">
                {sttActive ? "Stop Mic" : "Start Mic STT"}
              </Btn>
              <Btn variant="ghost" onClick={() => setTranscript([])}>
                Clear
              </Btn>
            </div>

            {partialTranscript && (
              <div className="bg-gray-900 border border-gray-700 rounded px-3 py-2 italic text-gray-400">
                🎙 {partialTranscript}…
              </div>
            )}

            <div className="space-y-1.5">
              {transcript.length === 0 ? (
                <p className="text-gray-600 text-center py-8">
                  Transcript will appear here.
                  <br />
                  Start mic STT or upload audio.
                </p>
              ) : (
                transcript.map((line, i) => (
                  <div key={i} className="text-xs">
                    <span className="text-blue-400 font-semibold mr-1.5">{line.speaker}:</span>
                    <span className={clsx("text-gray-200", !line.is_final && "text-gray-400 italic")}>
                      {line.text}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ── QUESTIONS TAB ─────────────────────────────────────────────────── */}
        {tab === "questions" && (
          <div className="p-3 space-y-2">
            <div className="flex gap-2">
              <Btn
                variant="outline"
                onClick={() => selectedWorkspace && selectedMeeting && loadQuestions(selectedWorkspace, selectedMeeting)}
              >
                ↻ Refresh
              </Btn>
            </div>

            {questions.length === 0 ? (
              <p className="text-gray-600 text-center py-8">
                No questions loaded. Select a meeting above.
              </p>
            ) : (
              <div className="space-y-1.5">
                {questions.map((q) => (
                  <div
                    key={q.id}
                    className={clsx(
                      "rounded-lg p-2 text-xs border",
                      q.status === "answered" && "bg-green-900/20 border-green-800",
                      q.status === "escalated" && "bg-red-900/20 border-red-800",
                      q.status === "asked" && "bg-blue-900/20 border-blue-800 animate-pulse",
                      q.status === "pending" && "bg-gray-800/50 border-gray-700",
                      q.status === "skipped" && "bg-gray-900 border-gray-800 opacity-50"
                    )}
                  >
                    <div className="flex items-start gap-1.5">
                      <span className="flex-shrink-0 mt-0.5">
                        {q.status === "answered"
                          ? "✅"
                          : q.status === "escalated"
                          ? "🔴"
                          : q.status === "asked"
                          ? "❓"
                          : q.status === "skipped"
                          ? "⏭"
                          : "•"}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-gray-200 leading-relaxed">{q.text}</p>
                        <div className="flex gap-2 mt-1 text-gray-500">
                          <span
                            className={clsx(
                              "px-1 rounded",
                              q.priority === "must_ask" ? "text-red-400" : "text-gray-500"
                            )}
                          >
                            {q.priority}
                          </span>
                          <span>{q.category}</span>
                          {q.proxy_allowed && <span className="text-green-500">proxy ✓</span>}
                          {q.human_only && <span className="text-orange-400">human only</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── SETTINGS TAB ──────────────────────────────────────────────────── */}
        {tab === "settings" && (
          <div className="p-3 space-y-4">
            <Section title="Connection">
              <div className="space-y-2">
                <div>
                  <label className="text-gray-400 mb-1 block">Backend URL</label>
                  <input
                    defaultValue={backendUrl}
                    onBlur={(e) => {
                      const url = e.target.value.trim().replace(/\/$/, "");
                      setBackendUrl(url);
                      chrome.storage.local.set({ backendUrl: url });
                    }}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-white focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Dot status={wsStatus} />
                  <span className="text-gray-400">WebSocket: {wsStatus}</span>
                </div>
              </div>
            </Section>

            <Section title="STT / TTS">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-gray-400">Web Speech STT</span>
                  <span
                    className={clsx(
                      "px-2 py-0.5 rounded text-xs",
                      sttRef.current?.isSupported
                        ? "bg-green-900 text-green-300"
                        : "bg-red-900 text-red-300"
                    )}
                  >
                    {sttRef.current?.isSupported ? "Supported" : "Not supported"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-400">Browser TTS (speechSynthesis)</span>
                  <span
                    className={clsx(
                      "px-2 py-0.5 rounded text-xs",
                      typeof speechSynthesis !== "undefined"
                        ? "bg-green-900 text-green-300"
                        : "bg-red-900 text-red-300"
                    )}
                  >
                    {typeof speechSynthesis !== "undefined" ? "Supported" : "Not supported"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-400">AI Voice (TTS)</span>
                  <Btn
                    variant={ttsEnabled ? "green" : "outline"}
                    onClick={() => setTtsEnabled((v) => !v)}
                  >
                    {ttsEnabled ? "Enabled" : "Disabled"}
                  </Btn>
                </div>
              </div>
            </Section>

            <Section title="Account">
              <div className="space-y-2">
                <p className="text-gray-300">{auth.user?.full_name}</p>
                <p className="text-gray-500">{auth.user?.email}</p>
                <Btn variant="red" onClick={logout}>
                  Sign Out
                </Btn>
              </div>
            </Section>

            <Section title="Detected Meeting">
              {detectedMeeting ? (
                <div className="space-y-1 text-gray-300">
                  <p>
                    <strong>Platform:</strong> {detectedMeeting.platform}
                  </p>
                  <p>
                    <strong>Meeting ID:</strong> {detectedMeeting.meetingId ?? "—"}
                  </p>
                  <p className="truncate">
                    <strong>URL:</strong> {detectedMeeting.url}
                  </p>
                  <p>
                    <strong>Participants:</strong>{" "}
                    {detectedMeeting.participants.join(", ") || "none detected"}
                  </p>
                </div>
              ) : (
                <p className="text-gray-600">No meeting detected on current tab.</p>
              )}
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}
