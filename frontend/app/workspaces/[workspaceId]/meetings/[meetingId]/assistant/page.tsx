"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { assistantApi, meetingApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Bot, Mic, AlertTriangle, ClipboardList, Radio, Square, Volume2, Ear } from "lucide-react";

type Ev = {
  id: number;
  type: string;
  speaker?: string;
  to?: string;
  text?: string;
  reason?: string;
  summary?: string;
  action_items?: unknown[];
  risks?: unknown[];
  decisions?: unknown[];
  audio_b64?: string;
};

export default function AssistantPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const meetingId = params.meetingId as string;

  const { data: meeting } = useQuery({
    queryKey: ["meeting", workspaceId, meetingId],
    queryFn: () => meetingApi.get(workspaceId, meetingId),
  });

  const [mode, setMode] = useState<"assistant" | "recorder">("assistant");
  const [meetingUrl, setMeetingUrl] = useState("");
  const [simulate, setSimulate] = useState(true);
  const [consent, setConsent] = useState(false);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<Ev[]>([]);
  const idRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);
  const audioQueue = useRef<string[]>([]);
  const playing = useRef(false);

  const push = (e: Omit<Ev, "id">) => setEvents((prev) => [...prev.slice(-300), { ...e, id: ++idRef.current }]);

  // Auto-scroll
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [events]);

  // Close the socket + stop audio when navigating away mid-session (prevents leaks).
  useEffect(() => () => {
    wsRef.current?.close();
    wsRef.current = null;
    playing.current = false;
    audioQueue.current = [];
  }, []);

  const playNext = () => {
    if (playing.current || audioQueue.current.length === 0) return;
    const next = audioQueue.current.shift()!;
    playing.current = true;
    const audio = new Audio(`data:audio/mp3;base64,${next}`);
    audio.onended = () => { playing.current = false; playNext(); };
    audio.onerror = () => { playing.current = false; playNext(); };
    audio.play().catch(() => { playing.current = false; });
  };

  const connectWs = () => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const token = localStorage.getItem("access_token") ?? "";
    const ws = new WebSocket(apiBase.replace(/^http/, "ws") + `/api/ws/meetings/${meetingId}?token=${token}`);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        const m = JSON.parse(e.data);
        if (m.type === "tts_audio" && m.audio_b64) {
          audioQueue.current.push(m.audio_b64);
          playNext();
        }
        push(m);
        if (m.type === "session_complete") {
          setRunning(false);
          ws.close();
        }
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => { wsRef.current = null; };
  };

  const start = async () => {
    if (!simulate && !meetingUrl) {
      toast.error("Enter a meeting link, or turn on Simulate to demo without a real call.");
      return;
    }
    try {
      if (!meeting?.proxy_consent_given) {
        if (!consent) {
          toast.error("Please confirm participant consent first.");
          return;
        }
        await meetingApi.update(workspaceId, meetingId, { proxy_consent_given: true });
      }
      setEvents([]);
      connectWs();
      await assistantApi.start(workspaceId, meetingId, {
        mode,
        meeting_url: meetingUrl || undefined,
        simulate,
        assistant_name: "AmMeeting",
      });
      setRunning(true);
      toast.success(`Assistant started in ${mode} mode`);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg || "Could not start assistant");
      wsRef.current?.close();
    }
  };

  const stop = async () => {
    try {
      await assistantApi.stop(workspaceId, meetingId);
      toast.success("Asked the assistant to wrap up");
    } catch {
      /* ignore */
    }
  };

  const needsConsent = meeting && !meeting.proxy_consent_given;

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href={`/workspaces/${workspaceId}/meetings/${meetingId}`}>
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Bot className="h-8 w-8 text-blue-400" /> Meeting Assistant
          </h1>
          <p className="text-slate-400 mt-1">
            Sends an AI agent to attend, listen, and {mode === "assistant" ? "reply" : "record"} — then summarize and leave.
          </p>
        </div>
      </div>

      {/* Config */}
      <Card className="bg-slate-900 border-slate-800 mb-6">
        <CardHeader className="pb-3">
          <CardTitle className="text-white text-base">Setup</CardTitle>
          <CardDescription className="text-slate-400">Choose how the assistant behaves in the meeting</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Mode */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              disabled={running}
              onClick={() => setMode("assistant")}
              className={`text-left rounded-xl border-2 p-4 transition-all ${mode === "assistant" ? "border-blue-600 bg-blue-900/20" : "border-slate-800 bg-slate-900/50 hover:border-slate-600"}`}
            >
              <div className="flex items-center gap-2 text-white font-medium"><Volume2 className="h-4 w-4 text-blue-400" /> Assistant</div>
              <p className="text-xs text-slate-400 mt-1">Listens and replies out loud — answers questions, escalates sensitive ones.</p>
            </button>
            <button
              type="button"
              disabled={running}
              onClick={() => setMode("recorder")}
              className={`text-left rounded-xl border-2 p-4 transition-all ${mode === "recorder" ? "border-blue-600 bg-blue-900/20" : "border-slate-800 bg-slate-900/50 hover:border-slate-600"}`}
            >
              <div className="flex items-center gap-2 text-white font-medium"><Ear className="h-4 w-4 text-green-400" /> Recorder</div>
              <p className="text-xs text-slate-400 mt-1">Stays silent — only records, transcribes, and summarizes at the end.</p>
            </button>
          </div>

          {/* Meeting link + simulate */}
          <div className="space-y-2">
            <label className="text-sm text-slate-300">Meeting link (Zoom / Meet / Teams)</label>
            <Input
              value={meetingUrl}
              onChange={(e) => setMeetingUrl(e.target.value)}
              placeholder="https://zoom.us/j/123… (or use Simulate to demo)"
              disabled={running || simulate}
              className="bg-slate-950 border-slate-700 text-white"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={simulate} disabled={running} onChange={(e) => setSimulate(e.target.checked)} className="accent-blue-500" />
            Simulate (demo with a scripted conversation — no real bot/credentials needed)
          </label>

          {needsConsent && (
            <label className="flex items-start gap-2 text-sm text-amber-200 bg-amber-900/20 border border-amber-800 rounded-lg p-3">
              <input type="checkbox" checked={consent} disabled={running} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 accent-amber-500" />
              I confirm all participants are aware an AI assistant will attend and record this meeting.
            </label>
          )}

          <div className="flex gap-3 pt-1">
            {!running ? (
              <Button onClick={start} className="bg-blue-600 hover:bg-blue-500">
                <Radio className="h-4 w-4 mr-2" /> Send the assistant in
              </Button>
            ) : (
              <Button onClick={stop} variant="outline" className="border-red-800 text-red-300 hover:bg-red-900/30">
                <Square className="h-4 w-4 mr-2" /> Wrap up &amp; leave
              </Button>
            )}
            {running && <Badge className="bg-green-900 text-green-300 animate-pulse self-center">● live</Badge>}
          </div>
        </CardContent>
      </Card>

      {/* Live feed */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-white text-base">Live</CardTitle>
        </CardHeader>
        <CardContent>
          <div ref={feedRef} className="h-[420px] overflow-y-auto space-y-2 pr-2">
            {events.length === 0 && <p className="text-slate-600 text-sm">Start the assistant to watch it listen and respond…</p>}
            {events.map((e) => (
              <EventRow key={e.id} e={e} />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function EventRow({ e }: { e: Ev }) {
  if (e.type === "transcript") {
    return (
      <div className="flex gap-2 text-sm">
        <Mic className="h-4 w-4 text-slate-500 shrink-0 mt-0.5" />
        <span className="text-slate-300"><b className="text-slate-200">{e.speaker}:</b> {e.text}</span>
      </div>
    );
  }
  if (e.type === "disclosure") {
    return <div className="text-sm text-blue-300 bg-blue-900/15 border border-blue-900 rounded-lg p-2">🤖 {e.text}</div>;
  }
  if (e.type === "assistant_reply") {
    return (
      <div className="flex gap-2 text-sm bg-blue-900/20 border border-blue-800 rounded-lg p-2">
        <Bot className="h-4 w-4 text-blue-400 shrink-0 mt-0.5" />
        <span className="text-blue-100"><b>Assistant{e.to ? ` → ${e.to}` : ""}:</b> {e.text}</span>
      </div>
    );
  }
  if (e.type === "escalation") {
    return (
      <div className="flex gap-2 text-sm bg-orange-900/20 border border-orange-800 rounded-lg p-2">
        <AlertTriangle className="h-4 w-4 text-orange-400 shrink-0 mt-0.5" />
        <span className="text-orange-200"><b>Escalated:</b> {e.reason}</span>
      </div>
    );
  }
  if (e.type === "summary") {
    return (
      <div className="text-sm bg-slate-800/60 border border-slate-700 rounded-lg p-3">
        <div className="flex items-center gap-2 text-white font-medium mb-1"><ClipboardList className="h-4 w-4 text-green-400" /> Summary</div>
        <p className="text-slate-300">{e.summary}</p>
        <p className="text-xs text-slate-500 mt-2">
          {(e.action_items?.length ?? 0)} action items · {(e.risks?.length ?? 0)} risks · {(e.decisions?.length ?? 0)} decisions
        </p>
      </div>
    );
  }
  if (e.type === "info" || e.type === "bot_status") {
    return <div className="text-xs text-slate-500">ℹ {e.text}</div>;
  }
  if (e.type === "error") {
    return <div className="text-sm text-red-300">⚠ {e.text}</div>;
  }
  return null;
}
