"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { calendarApi, meetingApi } from "@/lib/api-client";
import type { CalendarEvent } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft, Bot, Eye, Activity, Database, Calendar, Video } from "lucide-react";
import Link from "next/link";

const MODES = [
  {
    id: "shadow",
    label: "Shadow Assistant",
    description: "Silently guides you during the meeting — shows what to ask, tracks answers, provides context.",
    icon: Eye,
    color: "border-blue-700 bg-blue-900/20",
    recommended: false,
  },
  {
    id: "live_navigator",
    label: "Live Navigator",
    description: "Tracks questions, answers, decisions, and risks live during the meeting.",
    icon: Activity,
    color: "border-green-700 bg-green-900/20",
    recommended: false,
  },
  {
    id: "proxy",
    label: "Transparent Proxy",
    description: "AI attends the meeting as your authorized proxy, introduces itself, asks approved questions, escalates restricted topics to you.",
    icon: Bot,
    color: "border-purple-700 bg-purple-900/20",
    recommended: true,
  },
  {
    id: "data_collection",
    label: "Data Collector",
    description: "Structured interviewer for onboarding, research, or status collection.",
    icon: Database,
    color: "border-amber-700 bg-amber-900/20",
    recommended: false,
  },
];

export default function NewMeetingPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [mode, setMode] = useState("shadow");
  const [proxyConsent, setProxyConsent] = useState(false);
  const [meetingUrl, setMeetingUrl] = useState("");
  const [calendarEventId, setCalendarEventId] = useState<string | null>(null);
  const [scheduledAt, setScheduledAt] = useState<string | null>(null);
  const [autoJoin, setAutoJoin] = useState(false);

  const { data: calendarEvents } = useQuery({
    queryKey: ["calendar-events", workspaceId],
    queryFn: () => calendarApi.events(workspaceId),
  });

  const pickEvent = (ev: CalendarEvent) => {
    setTitle(ev.title || title);
    setCalendarEventId(ev.id);
    setScheduledAt(ev.start ?? null);
    if (ev.meet_link) setMeetingUrl(ev.meet_link);
    toast.success(`Imported "${ev.title}" from calendar`);
  };

  const mutation = useMutation({
    mutationFn: () =>
      meetingApi.create(workspaceId, {
        title,
        purpose: purpose || undefined,
        mode: mode as "shadow" | "proxy" | "live_navigator" | "data_collection",
        proxy_consent_given: mode === "proxy" ? proxyConsent : false,
        meeting_url: meetingUrl || undefined,
        calendar_event_id: calendarEventId || undefined,
        scheduled_at: scheduledAt || undefined,
        auto_join_enabled: mode === "proxy" ? autoJoin : false,
      }),
    onSuccess: (meeting) => {
      toast.success("Meeting created!");
      router.push(`/workspaces/${workspaceId}/meetings/${meeting.id}`);
    },
    onError: () => toast.error("Failed to create meeting"),
  });

  return (
    <div className="p-8 max-w-2xl">
      <Link href={`/workspaces/${workspaceId}`}>
        <Button variant="ghost" className="text-slate-400 hover:text-white mb-6 -ml-2">
          <ArrowLeft className="h-4 w-4 mr-2" /> Back
        </Button>
      </Link>

      <h1 className="text-3xl font-bold text-white mb-2">New Meeting</h1>
      <p className="text-slate-400 mb-8">Configure your meeting and choose how AmMeeting will assist you.</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (mode === "proxy" && !proxyConsent) {
            toast.error("Proxy consent is required to use Transparent Proxy mode.");
            return;
          }
          mutation.mutate();
        }}
        className="space-y-6"
      >
        {calendarEvents && calendarEvents.length > 0 && (
          <Card className="border-slate-700 bg-slate-900/50">
            <CardHeader className="pb-2">
              <CardTitle className="text-slate-200 text-sm flex items-center gap-2">
                <Calendar className="h-4 w-4 text-green-400" /> Import from your calendar
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {calendarEvents.map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => pickEvent(ev)}
                  className={`w-full text-left rounded-lg border p-3 transition-colors ${
                    calendarEventId === ev.id
                      ? "border-green-700 bg-green-900/20"
                      : "border-slate-800 bg-slate-900 hover:border-slate-600"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-white">{ev.title}</span>
                    {ev.meet_link && <Video className="h-4 w-4 text-blue-400" />}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {ev.start ? new Date(ev.start).toLocaleString() : "No time"} ·{" "}
                    {ev.attendees?.length ?? 0} attendees
                  </p>
                </button>
              ))}
            </CardContent>
          </Card>
        )}

        <div className="space-y-2">
          <Label className="text-slate-300">Meeting Title *</Label>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Client Dashboard Review"
            required
            className="bg-slate-900 border-slate-700 text-white"
          />
        </div>

        <div className="space-y-2">
          <Label className="text-slate-300 flex items-center gap-2">
            <Video className="h-4 w-4" /> Meeting Link (Zoom / Google Meet / Teams)
          </Label>
          <Input
            value={meetingUrl}
            onChange={(e) => setMeetingUrl(e.target.value)}
            placeholder="https://zoom.us/j/123456789"
            className="bg-slate-900 border-slate-700 text-white"
          />
          <p className="text-xs text-slate-500">
            Required for the AI bot to join the call. Auto-filled when you import a calendar event.
          </p>
        </div>

        <div className="space-y-2">
          <Label className="text-slate-300">Purpose</Label>
          <Textarea
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            placeholder="What is the goal of this meeting?"
            className="bg-slate-900 border-slate-700 text-white resize-none"
            rows={2}
          />
        </div>

        <div className="space-y-3">
          <Label className="text-slate-300">Meeting Mode</Label>
          <div className="grid grid-cols-1 gap-3">
            {MODES.map((m) => (
              <div
                key={m.id}
                onClick={() => setMode(m.id)}
                className={`relative rounded-xl border-2 p-4 cursor-pointer transition-all ${
                  mode === m.id ? m.color : "border-slate-800 bg-slate-900/50"
                }`}
              >
                {m.recommended && (
                  <span className="absolute top-3 right-3 text-xs px-2 py-0.5 bg-purple-800 text-purple-200 rounded-full">
                    Recommended
                  </span>
                )}
                <div className="flex items-start gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${mode === m.id ? "bg-white/10" : "bg-slate-800"}`}>
                    <m.icon className={`h-4 w-4 ${mode === m.id ? "text-white" : "text-slate-400"}`} />
                  </div>
                  <div>
                    <p className={`font-medium ${mode === m.id ? "text-white" : "text-slate-300"}`}>{m.label}</p>
                    <p className={`text-sm mt-0.5 ${mode === m.id ? "text-slate-300" : "text-slate-500"}`}>
                      {m.description}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {mode === "proxy" && (
          <Card className="border-purple-800 bg-purple-900/20">
            <CardHeader className="pb-2">
              <CardTitle className="text-purple-200 text-sm flex items-center gap-2">
                <Bot className="h-4 w-4" /> Proxy Consent Required
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-purple-300 text-sm">
                Before AmMeeting can attend as your proxy, all participants must be notified. 
                AmMeeting will introduce itself as: <em>&quot;I am AmMeeting, an authorized AI meeting assistant
                representing [your name]. I will not make final decisions on your behalf.&quot;</em>
              </p>
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={proxyConsent}
                  onChange={(e) => setProxyConsent(e.target.checked)}
                  className="mt-1 accent-purple-500"
                />
                <span className="text-sm text-purple-200">
                  I confirm that all meeting participants have been notified that an authorized AI assistant
                  will attend and that no recordings will be made without prior consent.
                </span>
              </label>

              <label className="flex items-start gap-3 cursor-pointer border-t border-purple-800/50 pt-3">
                <input
                  type="checkbox"
                  checked={autoJoin}
                  onChange={(e) => setAutoJoin(e.target.checked)}
                  className="mt-1 accent-purple-500"
                />
                <span className="text-sm text-purple-200">
                  <strong>Auto-join at start time.</strong> Automatically deploy the proxy bot when this
                  meeting begins (requires a meeting link and a scheduled time). Leave off to start it manually.
                </span>
              </label>
            </CardContent>
          </Card>
        )}

        <div className="flex gap-3 pt-2">
          <Button type="submit" disabled={mutation.isPending} className="flex-1">
            {mutation.isPending ? "Creating..." : "Create Meeting"}
          </Button>
        </div>
      </form>
    </div>
  );
}
