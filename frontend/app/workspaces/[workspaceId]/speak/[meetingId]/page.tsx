"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { speakApi, meetingApi, type SpeakState, type SpeakSummary } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Mic, Radio, Sparkles } from "lucide-react";

const PRIORITY_STYLE: Record<string, string> = {
  must: "bg-red-900/40 text-red-300",
  should: "bg-blue-900/40 text-blue-300",
  nice: "bg-slate-800 text-slate-400",
};

function pct(s: SpeakState | null) {
  if (!s || !s.progress.total) return 0;
  return Math.round((100 * s.progress.covered) / s.progress.total);
}

export default function SpeakSessionPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const meetingId = params.meetingId as string;

  const { data: meeting } = useQuery({
    queryKey: ["meeting", workspaceId, meetingId],
    queryFn: () => meetingApi.get(workspaceId, meetingId),
  });

  const [notes, setNotes] = useState("");
  const [state, setState] = useState<SpeakState | null>(null);
  const [summary, setSummary] = useState<SpeakSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load any existing points.
  useEffect(() => {
    speakApi.state(workspaceId, meetingId).then(setState).catch(() => {});
  }, [workspaceId, meetingId]);

  // Live view: poll state (updated by the extension's live ingest) for a presenter screen.
  useEffect(() => {
    if (!live) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(() => {
      speakApi.state(workspaceId, meetingId).then(setState).catch(() => {});
    }, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [live, workspaceId, meetingId]);

  const generate = async () => {
    if (!notes.trim()) return toast.error("Paste your notes or agenda first.");
    setBusy(true);
    try {
      setState(await speakApi.generate(workspaceId, meetingId, notes.trim()));
      setSummary(null);
      toast.success("Speaking points ready.");
    } catch {
      toast.error("Couldn't generate points — check the AI settings.");
    } finally {
      setBusy(false);
    }
  };

  const togglePoint = async (pointId: string, status: string) => {
    const next = status === "covered" ? "pending" : "covered";
    try {
      await speakApi.updatePoint(workspaceId, meetingId, pointId, { status: next });
      setState(await speakApi.state(workspaceId, meetingId));
    } catch {
      /* ignore */
    }
  };

  const finalize = async () => {
    setBusy(true);
    setLive(false);
    try {
      setSummary(await speakApi.finalize(workspaceId, meetingId));
      setState(await speakApi.state(workspaceId, meetingId));
    } catch {
      toast.error("Couldn't finalize.");
    } finally {
      setBusy(false);
    }
  };

  const stages = state ? Array.from(new Set(state.points.map((p) => p.stage))) : [];

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href={`/workspaces/${workspaceId}/speak`}>
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Mic className="h-6 w-6 text-green-400" /> {meeting?.title ?? "Speak session"}
          </h1>
          <p className="text-slate-400 text-sm">Prepare your points — the extension ticks them off live.</p>
        </div>
      </div>

      {(!state || state.points.length === 0) && (
        <Card className="bg-slate-900 border-slate-800 mb-6">
          <CardHeader>
            <CardTitle className="text-white text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-green-400" /> Prepare your speaking points
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={8}
              placeholder="Paste your notes, agenda, sermon outline, interview questions, or demo script…"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-green-500"
            />
            <Button onClick={generate} disabled={busy || !notes.trim()} className="gap-2">
              <Sparkles className="h-4 w-4" /> {busy ? "Structuring…" : "Generate speaking points"}
            </Button>
          </CardContent>
        </Card>
      )}

      {state && state.points.length > 0 && (
        <>
          <Card className="bg-slate-900 border-slate-800 mb-4">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-slate-300">
                  {state.progress.covered}/{state.progress.total} covered
                  {state.progress.must_remaining > 0 && (
                    <span className="text-amber-400"> · {state.progress.must_remaining} must-have{state.progress.must_remaining > 1 ? "s" : ""} left</span>
                  )}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant={live ? "default" : "outline"}
                    className={live ? "bg-green-700 hover:bg-green-600" : "border-slate-700 text-slate-300"}
                    onClick={() => setLive((v) => !v)}
                  >
                    <Radio className="h-4 w-4 mr-1" /> {live ? "Live view on" : "Live view"}
                  </Button>
                  <Button size="sm" variant="outline" className="border-slate-700 text-slate-300" onClick={finalize} disabled={busy}>
                    Finish &amp; summarize
                  </Button>
                </div>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-green-500 transition-all" style={{ width: `${pct(state)}%` }} />
              </div>
            </CardContent>
          </Card>

          {stages.map((stage) => (
            <div key={stage} className="mb-4">
              <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">{stage}</p>
              <div className="space-y-1.5">
                {state.points.filter((p) => p.stage === stage).map((p) => (
                  <div
                    key={p.id}
                    onClick={() => togglePoint(p.id, p.status)}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2 cursor-pointer border transition ${
                      p.status === "covered"
                        ? "bg-green-900/20 border-green-800"
                        : p.status === "missed"
                        ? "bg-red-900/20 border-red-800"
                        : "bg-slate-900 border-slate-800 hover:border-slate-600"
                    }`}
                  >
                    <span className="text-lg">
                      {p.status === "covered" ? "✅" : p.status === "missed" ? "❌" : p.priority === "must" ? "🔴" : "⚪"}
                    </span>
                    <span className={`flex-1 text-sm ${p.status === "covered" ? "line-through text-slate-500" : "text-slate-200"}`}>
                      {p.text}
                    </span>
                    <Badge className={`text-xs ${PRIORITY_STYLE[p.priority]}`}>{p.priority}</Badge>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {state.responses.length > 0 && (
            <Card className="bg-slate-900 border-slate-800 mb-4">
              <CardHeader className="pb-2"><CardTitle className="text-white text-sm">Audience responses</CardTitle></CardHeader>
              <CardContent className="space-y-1">
                {state.responses.map((r) => (
                  <p key={r.id} className="text-sm text-slate-300">
                    <span className="text-slate-500">{r.kind} · {r.speaker}:</span> {r.text}
                  </p>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {summary && (
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader><CardTitle className="text-white text-base">Session summary</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="text-slate-200">{summary.summary}</p>
            {summary.missed.length > 0 && (
              <div>
                <p className="text-slate-500 font-medium mb-1">Missed points</p>
                {summary.missed.map((m, i) => <p key={i} className="text-red-300">— {m}</p>)}
              </div>
            )}
            {summary.action_items.length > 0 && (
              <div>
                <p className="text-slate-500 font-medium mb-1">Action items</p>
                {summary.action_items.map((a, i) => <p key={i} className="text-slate-300">• {a.title}{a.owner ? ` — ${a.owner}` : ""}</p>)}
              </div>
            )}
            {summary.follow_ups.length > 0 && (
              <div>
                <p className="text-slate-500 font-medium mb-1">Follow-ups</p>
                {summary.follow_ups.map((f, i) => <p key={i} className="text-slate-300">• {f}</p>)}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
