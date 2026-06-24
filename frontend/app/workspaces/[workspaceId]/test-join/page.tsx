"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { meetingApi } from "@/lib/api-client";
import { BASE_URL } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Bot, Radio, Video } from "lucide-react";

type EventItem = { id: number; type: string; text: string; ts: string };

const STATUS_STYLE: Record<string, string> = {
  idle: "bg-slate-700 text-slate-300",
  starting: "bg-blue-900 text-blue-300 animate-pulse",
  creating: "bg-blue-900 text-blue-300 animate-pulse",
  joining: "bg-yellow-900 text-yellow-300 animate-pulse",
  in_meeting: "bg-green-900 text-green-300 animate-pulse",
  scheduled: "bg-purple-900 text-purple-300",
  done: "bg-slate-700 text-slate-300",
  error: "bg-red-900 text-red-300",
};

export default function TestJoinPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;

  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"recorder" | "assistant">("recorder");
  const [whenMode, setWhenMode] = useState<"now" | "schedule">("now");
  const [scheduleAt, setScheduleAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [botStatus, setBotStatus] = useState("idle");
  const [events, setEvents] = useState<EventItem[]>([]);
  const [meetingId, setMeetingId] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const idRef = useRef(0);
  const endRef = useRef<HTMLDivElement | null>(null);

  const addEvent = (type: string, text: string) =>
    setEvents((e) => [...e.slice(-250), { id: ++idRef.current, type, text, ts: new Date().toLocaleTimeString() }]);

  useEffect(() => () => wsRef.current?.close(), []);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [events]);

  const connectWs = (mid: string) => {
    wsRef.current?.close();
    const ws = new WebSocket(`${BASE_URL.replace(/^http/, "ws")}/api/ws/meetings/${mid}`);
    wsRef.current = ws;
    ws.onopen = () => addEvent("info", "Live channel connected — waiting for the bot…");
    ws.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data) as Record<string, unknown>;
        if (d.type === "bot_status" && typeof d.status === "string") setBotStatus(d.status);
        const text =
          (d.text as string) ||
          (d.answer as string) ||
          (d.reason as string) ||
          (d.speaker ? `${d.speaker}: ${(d.text as string) ?? ""}` : "");
        addEvent((d.type as string) || "event", text || JSON.stringify(d));
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = () => addEvent("info", "Live channel closed");
    ws.onerror = () => addEvent("error", "Live channel error");
  };

  const submit = async () => {
    if (!url.trim()) return toast.error("Paste a meeting link first.");
    if (whenMode === "schedule" && !scheduleAt) return toast.error("Pick a date & time.");
    setSubmitting(true);
    setEvents([]);
    setBotStatus("starting");
    try {
      const when = whenMode === "now" ? "now" : new Date(scheduleAt).toISOString();
      const res = await meetingApi.testJoin(workspaceId, { meeting_url: url.trim(), when, mode });
      setMeetingId(res.meeting_id);
      addEvent("info", res.message);
      if (res.note) toast.warning(res.note);
      if (res.joining) {
        connectWs(res.meeting_id);
      } else {
        setBotStatus("scheduled");
        connectWs(res.meeting_id); // stream events when the scheduler fires
      }
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(detail || "Failed to start the bot.");
      setBotStatus("error");
      addEvent("error", detail || "Failed to start the bot.");
    } finally {
      setSubmitting(false);
    }
  };

  const stop = async () => {
    if (meetingId) {
      try {
        await meetingApi.stopAssistant(workspaceId, meetingId);
      } catch {
        /* best effort */
      }
    }
    wsRef.current?.close();
    setBotStatus("done");
    addEvent("info", "Stopped.");
  };

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-3xl font-bold text-white flex items-center gap-3">
        <Radio className="h-8 w-8 text-green-400" /> Live Test — Join a Meeting
      </h1>
      <p className="text-slate-400 mt-1 mb-6">
        Paste a meeting link and send the AI bot to attend — right now or at a scheduled time. No simulation.
      </p>

      <Card className="bg-slate-900 border-slate-800 mb-6">
        <CardHeader>
          <CardTitle className="text-white text-base flex items-center gap-2">
            <Video className="h-4 w-4 text-blue-400" /> Meeting
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label className="text-slate-300">Meeting link</Label>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://meet.ffmuc.net/Room  ·  https://meet.google.com/abc-defg-hij  ·  Zoom/Teams link"
              className="bg-slate-800 border-slate-700 text-white"
            />
            <p className="text-xs text-slate-500">
              Jitsi & open links join immediately. Google Meet needs the signed-in bot (one-time
              <code className="text-slate-400"> npm run google-login</code>) — otherwise Google denies it and you&apos;ll see that below.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label className="text-slate-300">Mode</Label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as "recorder" | "assistant")}
                className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-white"
              >
                <option value="recorder">Recorder — listen &amp; take notes (silent)</option>
                <option value="assistant">Assistant — listen &amp; speak when addressed</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-slate-300">When</Label>
              <select
                value={whenMode}
                onChange={(e) => setWhenMode(e.target.value as "now" | "schedule")}
                className="w-full bg-slate-800 border border-slate-700 rounded-md px-3 py-2 text-sm text-white"
              >
                <option value="now">Join now</option>
                <option value="schedule">Schedule for…</option>
              </select>
            </div>
          </div>

          {whenMode === "schedule" && (
            <div className="space-y-1">
              <Label className="text-slate-300">Date &amp; time</Label>
              <Input
                type="datetime-local"
                value={scheduleAt}
                onChange={(e) => setScheduleAt(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
              />
              <p className="text-xs text-slate-500">The auto-join scheduler deploys the bot around this time.</p>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button onClick={submit} disabled={submitting} className="gap-2">
              <Bot className="h-4 w-4" />
              {submitting ? "Starting…" : whenMode === "now" ? "Join now" : "Schedule join"}
            </Button>
            {(botStatus === "in_meeting" || botStatus === "joining" || botStatus === "scheduled") && (
              <Button variant="outline" onClick={stop} className="border-slate-700 text-slate-300">
                Stop
              </Button>
            )}
            <Badge className={`ml-auto ${STATUS_STYLE[botStatus] ?? "bg-slate-700 text-slate-300"}`}>
              {botStatus.replace(/_/g, " ")}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-white text-base">Live status</CardTitle>
        </CardHeader>
        <CardContent>
          {events.length === 0 ? (
            <p className="text-slate-500 text-sm">Events will stream here once the bot starts.</p>
          ) : (
            <div className="space-y-1 max-h-80 overflow-y-auto text-sm font-mono">
              {events.map((ev) => (
                <div key={ev.id} className="flex gap-2">
                  <span className="text-slate-600 shrink-0">{ev.ts}</span>
                  <span
                    className={
                      ev.type === "error"
                        ? "text-red-400"
                        : ev.type === "bot_status"
                        ? "text-cyan-300"
                        : ev.type === "transcript"
                        ? "text-slate-200"
                        : "text-slate-400"
                    }
                  >
                    <span className="uppercase text-[10px] mr-1 opacity-60">{ev.type}</span>
                    {ev.text}
                  </span>
                </div>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
