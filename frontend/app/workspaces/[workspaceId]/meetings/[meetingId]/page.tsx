"use client";

import { useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { isAxiosError } from "axios";
import { delegateApi, meetingApi, questionApi, reportApi } from "@/lib/api-client";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import {
  ArrowLeft, Upload, Zap, FileText, CheckCircle, AlertTriangle,
  Clock, User, Target, RefreshCw, Send, Shield, Bot, Eye,
  History, HelpCircle
} from "lucide-react";
import Link from "next/link";
import type { DelegateSession, DelegateStage, Meeting, PrepBrief, Question, ProxyEvent, Report } from "@/lib/types";
import { BASE_URL } from "@/lib/api";

const PRIORITY_COLORS: Record<string, string> = {
  must_ask: "bg-red-900/50 border-red-700 text-red-300",
  if_time: "bg-yellow-900/50 border-yellow-700 text-yellow-300",
  ask_later: "bg-slate-800 border-slate-700 text-slate-400",
  answered: "bg-green-900/50 border-green-700 text-green-300",
  needs_human: "bg-orange-900/50 border-orange-700 text-orange-300",
};

const CATEGORY_ICONS: Record<string, string> = {
  status: "📊",
  blocker: "🚧",
  ownership: "👤",
  deadline: "📅",
  client: "🤝",
  decision: "⚖️",
  risk: "⚠️",
  general: "💬",
};

const STATUS_ICONS: Record<string, typeof CheckCircle> = {
  answered: CheckCircle,
  escalated: AlertTriangle,
  asked: Clock,
  pending: Clock,
  skipped: Eye,
};

export default function MeetingPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const meetingId = params.meetingId as string;
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [proxyEvents, setProxyEvents] = useState<ProxyEvent[]>([]);
  const [proxyRunning, setProxyRunning] = useState(false);
  const [activeTab, setActiveTab] = useState("prep");

  const { data: meeting } = useQuery({
    queryKey: ["meeting", workspaceId, meetingId],
    queryFn: () => meetingApi.get(workspaceId, meetingId),
  });

  const { data: prepBrief, isLoading: prepLoading } = useQuery({
    queryKey: ["prep-brief", workspaceId, meetingId],
    queryFn: () => meetingApi.getPrepBrief(workspaceId, meetingId),
  });

  const { data: questions, isLoading: questionsLoading } = useQuery({
    queryKey: ["questions", workspaceId, meetingId],
    queryFn: () => questionApi.list(workspaceId, meetingId),
  });

  const { data: reports } = useQuery({
    queryKey: ["reports", workspaceId, meetingId],
    queryFn: () => reportApi.list(workspaceId, meetingId),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => meetingApi.uploadContext(workspaceId, meetingId, file),
    onSuccess: () => {
      toast.success("Context uploaded. Processing in background...");
      qc.invalidateQueries({ queryKey: ["prep-brief", workspaceId, meetingId] });
    },
    onError: () => toast.error("Upload failed"),
  });

  const generateQsMutation = useMutation({
    mutationFn: () => meetingApi.generateQuestions(workspaceId, meetingId),
    onSuccess: (d) => {
      toast.success(`Generated ${d.generated} questions!`);
      qc.invalidateQueries({ queryKey: ["questions", workspaceId, meetingId] });
      qc.invalidateQueries({ queryKey: ["prep-brief", workspaceId, meetingId] });
      setActiveTab("questions");
    },
    onError: () => toast.error("Question generation failed"),
  });

  const updateQuestionMutation = useMutation({
    mutationFn: ({ qId, data }: { qId: string; data: Partial<Question> }) =>
      questionApi.update(workspaceId, meetingId, qId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["questions", workspaceId, meetingId] }),
  });

  const generateReportMutation = useMutation({
    mutationFn: () => reportApi.generate(workspaceId, meetingId),
    onSuccess: () => {
      toast.success("Report generated!");
      qc.invalidateQueries({ queryKey: ["reports", workspaceId, meetingId] });
      setActiveTab("report");
    },
    onError: () => toast.error("Report generation failed"),
  });

  const startProxy = () => {
    if (!meeting?.proxy_consent_given) {
      toast.error("Proxy consent must be enabled before starting.");
      return;
    }
    setProxyEvents([]);
    setProxyRunning(true);
    setActiveTab("proxy");

    const token = localStorage.getItem("access_token");
    if (!token) {
      toast.error("Your session expired. Please sign in again.");
      setProxyRunning(false);
      return;
    }
    const url = `${BASE_URL}/api/workspaces/${workspaceId}/meetings/${meetingId}/proxy/start?simulate=true`;

    // Streamed SSE over fetch (EventSource can't send the auth header).
    fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).then(async (res) => {
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        toast.error(detail?.detail || `Couldn't start the proxy (${res.status}).`);
        setProxyRunning(false);
        return;
      }
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        setProxyRunning(false);
        return;
      }
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event: ProxyEvent = JSON.parse(line.slice(6));
              setProxyEvents((prev) => [...prev, event]);
              if (event.type === "report_ready") {
                qc.invalidateQueries({ queryKey: ["reports", workspaceId, meetingId] });
                qc.invalidateQueries({ queryKey: ["questions", workspaceId, meetingId] });
              }
            } catch {}
          }
        }
      }
      setProxyRunning(false);
    }).catch(() => setProxyRunning(false));
  };

  const answeredCount = questions?.filter((q) => q.status === "answered").length ?? 0;
  const totalCount = questions?.length ?? 0;

  const latestReport: Report | null = reports?.[0] ?? null;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="px-8 py-4">
          <div className="flex items-center gap-3 mb-1">
            <Link href={`/workspaces/${workspaceId}`}>
              <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white -ml-2">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <h1 className="text-xl font-semibold text-white">{meeting?.title ?? "Loading..."}</h1>
            {meeting && (
              <Badge
                className={`text-xs ${
                  meeting.mode === "proxy" ? "bg-purple-900 text-purple-300" :
                  meeting.mode === "live_navigator" ? "bg-green-900 text-green-300" :
                  "bg-blue-900 text-blue-300"
                }`}
              >
                {meeting.mode === "proxy" ? <><Bot className="h-3 w-3 mr-1 inline" /> Proxy</> :
                 meeting.mode === "live_navigator" ? "Live Navigator" : "Shadow"}
              </Badge>
            )}
          </div>
          {meeting?.purpose && <p className="text-slate-400 text-sm pl-8">{meeting.purpose}</p>}
        </div>
      </div>

      <div className="flex-1 p-8">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="bg-slate-900 border border-slate-800 mb-6">
            <TabsTrigger value="prep" className="data-[state=active]:bg-slate-800">
              <FileText className="h-4 w-4 mr-2" /> Prep Brief
            </TabsTrigger>
            <TabsTrigger value="questions" className="data-[state=active]:bg-slate-800">
              <Target className="h-4 w-4 mr-2" /> Questions
              {totalCount > 0 && (
                <Badge className="ml-1.5 bg-slate-700 text-slate-300 text-xs">{totalCount}</Badge>
              )}
            </TabsTrigger>
            {meeting?.mode === "proxy" && (
              <TabsTrigger value="proxy" className="data-[state=active]:bg-slate-800">
                <Bot className="h-4 w-4 mr-2" /> Proxy Room
              </TabsTrigger>
            )}
            <TabsTrigger value="report" className="data-[state=active]:bg-slate-800">
              <FileText className="h-4 w-4 mr-2" /> Report
              {latestReport && <Badge className="ml-1.5 bg-green-800 text-green-300 text-xs">Ready</Badge>}
            </TabsTrigger>
          </TabsList>

          {/* === PREP BRIEF TAB === */}
          <TabsContent value="prep" className="space-y-6">
            {/* Upload + Generate row */}
            <div className="flex items-center gap-3 flex-wrap">
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadMutation.isPending}
                className="border-slate-700 text-slate-300"
              >
                <Upload className="h-4 w-4 mr-2" />
                {uploadMutation.isPending ? "Uploading..." : "Upload Previous Transcript"}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.pdf,.docx,.md"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadMutation.mutate(f);
                }}
              />
              <Button
                onClick={() => generateQsMutation.mutate()}
                disabled={generateQsMutation.isPending}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <Zap className="h-4 w-4 mr-2" />
                {generateQsMutation.isPending ? "Generating..." : "Generate Smart Questions"}
              </Button>
            </div>

            {prepLoading ? (
              <Card className="bg-slate-900 border-slate-800 animate-pulse h-64" />
            ) : prepBrief ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Previous summary */}
                {prepBrief.previous_summary && (
                  <Card className="bg-slate-900 border-slate-800 lg:col-span-2">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-white text-sm flex items-center gap-2">
                        <RefreshCw className="h-4 w-4 text-blue-400" /> Previous Meeting Summary
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-slate-300 text-sm leading-relaxed">{prepBrief.previous_summary}</p>
                    </CardContent>
                  </Card>
                )}

                {/* R1 "Remember": commitments made in earlier meetings */}
                {(prepBrief.commitments?.length ?? 0) > 0 && (
                  <Card className="bg-slate-900 border-slate-800">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-white text-sm flex items-center gap-2">
                        <History className="h-4 w-4 text-amber-400" /> You Promised Last Time
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {prepBrief.commitments.map((c) => (
                        <div key={c.id} className="border border-slate-800 rounded-lg p-3">
                          <p className="text-sm text-slate-300">{c.title}</p>
                          <div className="flex items-center gap-3 mt-1 flex-wrap text-xs text-slate-500">
                            {c.owner && <span>Owner: {c.owner}</span>}
                            {c.deadline && <span>Due: {c.deadline}</span>}
                          </div>
                          <p className="text-xs text-slate-500 mt-1">
                            From: {c.meeting_title}
                            {c.meeting_date ? ` · ${new Date(c.meeting_date).toLocaleDateString()}` : ""}
                          </p>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* R1 "Remember": questions left unanswered in earlier meetings */}
                {(prepBrief.open_questions?.length ?? 0) > 0 && (
                  <Card className="bg-slate-900 border-slate-800">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-white text-sm flex items-center gap-2">
                        <HelpCircle className="h-4 w-4 text-blue-400" /> Still Unanswered
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {prepBrief.open_questions.map((q) => (
                        <div key={q.id} className="flex items-start gap-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-2 flex-shrink-0" />
                          <div>
                            <p className="text-sm text-slate-300">{q.text}</p>
                            <p className="text-xs text-slate-500 mt-0.5">From: {q.meeting_title}</p>
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* Attendees */}
                <Card className="bg-slate-900 border-slate-800">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-white text-sm flex items-center gap-2">
                      <User className="h-4 w-4 text-green-400" /> Attendees ({prepBrief.attendees.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {prepBrief.attendees.map((a, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0">
                          <span className="text-xs text-slate-300">{a.name.charAt(0)}</span>
                        </div>
                        <div>
                          <p className="text-sm text-white">{a.name}</p>
                          {a.role && <p className="text-xs text-slate-500">{a.role}</p>}
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                {/* Jira tickets */}
                <Card className="bg-slate-900 border-slate-800">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-white text-sm flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-400" /> Pending Jira Items
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {prepBrief.pending_jira_tickets.length === 0 ? (
                      <p className="text-slate-500 text-sm">No pending tickets</p>
                    ) : (
                      prepBrief.pending_jira_tickets.map((t) => (
                        <div key={t.key} className="border border-slate-800 rounded-lg p-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-mono text-blue-400">{t.key}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              t.status === "In Progress" ? "bg-blue-900 text-blue-300" :
                              t.status === "Review" ? "bg-yellow-900 text-yellow-300" :
                              "bg-slate-800 text-slate-400"
                            }`}>{t.status}</span>
                          </div>
                          <p className="text-sm text-slate-300">{t.summary}</p>
                          <p className="text-xs text-slate-500 mt-1">Owner: {t.assignee}</p>
                          {t.blockers?.length > 0 && (
                            <p className="text-xs text-red-400 mt-1">⚠ {t.blockers[0]}</p>
                          )}
                        </div>
                      ))
                    )}
                  </CardContent>
                </Card>

                {/* Open action items */}
                {prepBrief.open_action_items.length > 0 && (
                  <Card className="bg-slate-900 border-slate-800">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-white text-sm flex items-center gap-2">
                        <CheckCircle className="h-4 w-4 text-purple-400" /> Open Action Items
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {prepBrief.open_action_items.slice(0, 5).map((ai) => (
                        <div key={ai.id} className="flex items-start gap-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-purple-400 mt-2 flex-shrink-0" />
                          <div>
                            <p className="text-sm text-slate-300">{ai.title}</p>
                            {ai.owner && <p className="text-xs text-slate-500">Owner: {ai.owner}</p>}
                            {ai.deadline && <p className="text-xs text-slate-500">Due: {ai.deadline}</p>}
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* Suggested agenda */}
                <Card className="bg-slate-900 border-slate-800">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-white text-sm flex items-center gap-2">
                      <FileText className="h-4 w-4 text-cyan-400" /> Suggested Agenda
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ol className="space-y-2">
                      {prepBrief.suggested_agenda.map((item, i) => (
                        <li key={i} className="flex gap-3 text-sm text-slate-300">
                          <span className="text-slate-600 flex-shrink-0">{i + 1}.</span>
                          {item}
                        </li>
                      ))}
                    </ol>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card className="bg-slate-900 border-slate-800 border-dashed">
                <CardContent className="p-10 text-center">
                  <Upload className="h-10 w-10 text-slate-600 mx-auto mb-3" />
                  <p className="text-slate-400 mb-2">Upload a previous meeting transcript to get started</p>
                  <p className="text-slate-500 text-sm">Supports .txt, .pdf, .docx files</p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* === QUESTIONS TAB === */}
          <TabsContent value="questions">
            {totalCount > 0 && (
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm text-slate-400">
                    {answeredCount} of {totalCount} questions answered
                  </p>
                  {meeting?.mode === "proxy" && (
                    <Button
                      size="sm"
                      className="bg-purple-600 hover:bg-purple-700"
                      onClick={() => {
                        const pending = questions?.filter((q) => !q.human_only && !q.do_not_ask).map((q) => q.id) ?? [];
                        questionApi.bulkApproveProxy(workspaceId, meetingId, pending).then(() => {
                          toast.success("All eligible questions approved for proxy");
                          qc.invalidateQueries({ queryKey: ["questions", workspaceId, meetingId] });
                        });
                      }}
                    >
                      <Bot className="h-4 w-4 mr-2" /> Approve All for Proxy
                    </Button>
                  )}
                </div>
                <Progress value={(answeredCount / totalCount) * 100} className="h-2" />
              </div>
            )}

            {questionsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => <Card key={i} className="bg-slate-900 border-slate-800 animate-pulse h-20" />)}
              </div>
            ) : questions?.length === 0 ? (
              <Card className="bg-slate-900 border-slate-800 border-dashed">
                <CardContent className="p-10 text-center">
                  <Target className="h-10 w-10 text-slate-600 mx-auto mb-3" />
                  <p className="text-slate-400 mb-5">No questions yet. Generate smart questions from your context.</p>
                  <Button onClick={() => generateQsMutation.mutate()} disabled={generateQsMutation.isPending} className="bg-blue-600 hover:bg-blue-700">
                    <Zap className="h-4 w-4 mr-2" /> Generate Questions
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {(["must_ask", "if_time", "ask_later", "answered", "needs_human"] as const).map((group) => {
                  const groupQs = questions?.filter((q) => q.priority === group) ?? [];
                  if (groupQs.length === 0) return null;
                  const groupLabel = group === "must_ask" ? "Must Ask" : group === "if_time" ? "If Time Allows" : group === "ask_later" ? "Ask Later" : group === "answered" ? "Answered" : "Needs Human";
                  return (
                    <div key={group}>
                      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 px-1">
                        {groupLabel} ({groupQs.length})
                      </h3>
                      <div className="space-y-2 mb-4">
                        {groupQs.map((q) => (
                          <QuestionCard
                            key={q.id}
                            question={q}
                            showProxy={meeting?.mode === "proxy"}
                            onUpdate={(data) => updateQuestionMutation.mutate({ qId: q.id, data })}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </TabsContent>

          {/* === PROXY ROOM TAB === */}
          {meeting?.mode === "proxy" && (
            <TabsContent value="proxy">
              <ProxyRoom
                meeting={meeting}
                questions={questions ?? []}
                proxyEvents={proxyEvents}
                proxyRunning={proxyRunning}
                onStart={startProxy}
              />
            </TabsContent>
          )}

          {/* === REPORT TAB === */}
          <TabsContent value="report">
            <ReportTab
              latestReport={latestReport}
              onGenerate={() => generateReportMutation.mutate()}
              generating={generateReportMutation.isPending}
              workspaceId={workspaceId}
              meetingId={meetingId}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

// ── Question Card ──────────────────────────────────────────────────────────────

function QuestionCard({
  question,
  showProxy,
  onUpdate,
}: {
  question: Question;
  showProxy: boolean;
  onUpdate: (data: Partial<Question>) => void;
}) {
  const statusColor =
    question.status === "answered" ? "text-green-400" :
    question.status === "escalated" ? "text-orange-400" :
    "text-slate-500";

  return (
    <div className={`rounded-xl border p-4 transition-all ${
      question.do_not_ask ? "opacity-40" : ""
    } ${PRIORITY_COLORS[question.priority] ?? "border-slate-800 bg-slate-900"}`}>
      <div className="flex items-start gap-3">
        <span className="text-lg flex-shrink-0">{CATEGORY_ICONS[question.category] ?? "💬"}</span>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-medium ${question.status === "answered" ? "line-through text-slate-500" : "text-white"}`}>
            {question.text}
          </p>
          {question.source_context && (
            <p className="text-xs text-slate-500 mt-1">{question.source_context}</p>
          )}
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {question.confidence && (
              <span className="text-xs text-slate-500">
                {Math.round(question.confidence * 100)}% confidence
              </span>
            )}
            <span className={`text-xs ${statusColor}`}>{question.status}</span>
          </div>
        </div>

        {showProxy && (
          <div className="flex flex-col gap-1 items-end flex-shrink-0">
            {question.human_only ? (
              <Badge className="bg-orange-900 text-orange-300 text-xs whitespace-nowrap">
                <Shield className="h-3 w-3 mr-1" /> Human Only
              </Badge>
            ) : question.proxy_allowed ? (
              <Badge className="bg-purple-900 text-purple-300 text-xs whitespace-nowrap">
                <Bot className="h-3 w-3 mr-1" /> Proxy
              </Badge>
            ) : (
              <button
                onClick={() => onUpdate({ proxy_allowed: true })}
                className="text-xs text-slate-500 hover:text-purple-400 transition-colors whitespace-nowrap"
              >
                + Allow proxy
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Proxy Room ─────────────────────────────────────────────────────────────────

function ProxyRoom({
  meeting,
  questions,
  proxyEvents,
  proxyRunning,
  onStart,
}: {
  meeting: NonNullable<ReturnType<typeof useQuery<import("@/lib/types").Meeting>>["data"]>;
  questions: Question[];
  proxyEvents: ProxyEvent[];
  proxyRunning: boolean;
  onStart: () => void;
}) {
  const approvedCount = questions.filter((q) => q.proxy_allowed && !q.do_not_ask).length;
  const humanOnlyCount = questions.filter((q) => q.human_only).length;

  const evtTypeIcon: Record<string, string> = {
    disclosure: "🔔",
    asking: "❓",
    answered: "✅",
    escalation: "⚠️",
    clarifying: "🔍",
    session_complete: "🎉",
    report_ready: "📄",
    info: "ℹ️",
    error: "❌",
  };

  return (
    <div className="space-y-6">
      {/* Consent banner */}
      <Card className="border-purple-800 bg-purple-900/20">
        <CardContent className="p-4 flex items-start gap-3">
          <Bot className="h-5 w-5 text-purple-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-purple-200 text-sm font-medium">Transparent Proxy Mode</p>
            <p className="text-purple-300 text-sm mt-1">
              AmMeeting will introduce itself as your authorized AI assistant, ask all proxy-approved questions, 
              escalate restricted topics (budget/legal/HR), and never make final decisions on your behalf.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-purple-300">{approvedCount}</p>
            <p className="text-xs text-slate-400 mt-1">Proxy-approved questions</p>
          </CardContent>
        </Card>
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-orange-300">{humanOnlyCount}</p>
            <p className="text-xs text-slate-400 mt-1">Human-only questions</p>
          </CardContent>
        </Card>
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-4 text-center">
            <p className="text-2xl font-bold text-green-300">{proxyEvents.filter((e) => e.type === "answered").length}</p>
            <p className="text-xs text-slate-400 mt-1">Questions answered</p>
          </CardContent>
        </Card>
      </div>

      {/* Start button */}
      {proxyEvents.length === 0 && !proxyRunning && (
        <div className="text-center py-8">
          <p className="text-slate-400 mb-6">
            Ready to start the proxy session with {approvedCount} approved questions.
            {humanOnlyCount > 0 && ` ${humanOnlyCount} human-only questions will be skipped.`}
          </p>
          <Button
            onClick={onStart}
            size="lg"
            className="bg-purple-600 hover:bg-purple-700 px-8"
            disabled={approvedCount === 0}
          >
            <Bot className="h-5 w-5 mr-2" />
            Start Proxy Session (Simulated)
          </Button>
          <Link
            href={`/workspaces/${meeting.workspace_id}/meetings/${meeting.id}/live`}
            className="inline-flex items-center gap-2 ml-4 bg-green-700 hover:bg-green-600 text-white rounded-lg px-6 py-2.5 text-sm font-semibold transition"
          >
            🚀 Go Live (Real Meeting Bot)
          </Link>
          <Link
            href={`/workspaces/${meeting.workspace_id}/meetings/${meeting.id}/assistant`}
            className="inline-flex items-center gap-2 ml-4 bg-blue-700 hover:bg-blue-600 text-white rounded-lg px-6 py-2.5 text-sm font-semibold transition"
          >
            🤖 Meeting Assistant (listen &amp; reply / record)
          </Link>
          {approvedCount === 0 && (
            <p className="text-orange-400 text-sm mt-3">
              No questions are approved for proxy. Go to Questions tab and enable proxy for at least one question.
            </p>
          )}
        </div>
      )}

      {/* R2 "Delegate": AI attends on your behalf */}
      <DelegateCard meeting={meeting} />

      {/* Event stream */}
      {(proxyEvents.length > 0 || proxyRunning) && (
        <Card className="bg-slate-950 border-slate-800">
          <CardHeader className="pb-3 flex flex-row items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${proxyRunning ? "bg-green-400 animate-pulse" : "bg-slate-600"}`} />
            <CardTitle className="text-white text-sm">
              {proxyRunning ? "Proxy session in progress..." : "Session complete"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2">
              {proxyEvents.map((evt, i) => (
                <div key={i} className={`rounded-lg p-3 text-sm border ${
                  evt.type === "disclosure" ? "bg-blue-900/20 border-blue-800 text-blue-200" :
                  evt.type === "asking" ? "bg-slate-900 border-slate-700 text-white" :
                  evt.type === "answered" ? "bg-green-900/20 border-green-800 text-green-200" :
                  evt.type === "escalation" ? "bg-orange-900/20 border-orange-800 text-orange-200" :
                  evt.type === "clarifying" ? "bg-cyan-900/20 border-cyan-800 text-cyan-200" :
                  evt.type === "session_complete" ? "bg-purple-900/20 border-purple-800 text-purple-200" :
                  "bg-slate-900 border-slate-800 text-slate-400"
                }`}>
                  <div className="flex items-start gap-2">
                    <span className="flex-shrink-0">{evtTypeIcon[evt.type] ?? "•"}</span>
                    <div className="flex-1">
                      {evt.type === "asking" && (
                        <div>
                          <p className="font-medium text-white mb-1">AmMeeting asks:</p>
                          <p className="italic">&quot;{evt.text}&quot;</p>
                        </div>
                      )}
                      {evt.type === "answered" && (
                        <div>
                          <p className="font-medium text-green-300 mb-1">Answer captured:</p>
                          <p>{evt.answer}</p>
                        </div>
                      )}
                      {evt.type === "escalation" && (
                        <div>
                          <p className="font-medium text-orange-300 mb-1">⚠ Escalated to human</p>
                          <p>{evt.reason}</p>
                          {evt.answer_preview && <p className="text-xs mt-1 opacity-70">Preview: {evt.answer_preview}</p>}
                        </div>
                      )}
                      {evt.type === "disclosure" && (
                        <div>
                          <p className="font-medium mb-1">AmMeeting introduction:</p>
                          <p className="italic">&quot;{evt.text}&quot;</p>
                        </div>
                      )}
                      {(evt.type === "clarifying" || evt.type === "info" || evt.type === "session_complete") && (
                        <p>{evt.text}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              {proxyRunning && (
                <div className="flex items-center gap-2 text-slate-400 text-sm">
                  <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" />
                  Processing...
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Delegate Card (R2) ─────────────────────────────────────────────────────────

const DELEGATE_STAGE_OPTIONS: { value: DelegateStage; label: string; description: string }[] = [
  { value: "silent", label: "Silent", description: "Joins, discloses, records, reports" },
  { value: "briefed", label: "Briefed", description: "Also delivers your approved updates and asks your prepared questions" },
];

const DELEGATE_STATUS_TEXT: Record<string, string> = {
  created: "Delegate session created — waiting to join…",
  joining: "Delegate is joining the meeting…",
  active: "Delegate is in the meeting",
  leaving: "Delegate is leaving the meeting…",
  done: "Delegate session complete",
  error: "Delegate session failed",
};

function delegateErrorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const data = err.response?.data as { detail?: unknown } | undefined;
    if (typeof data?.detail === "string" && data.detail) return data.detail;
    switch (err.response?.status) {
      case 403:
        return "Proxy consent must be enabled before the delegate can join.";
      case 409:
        return "A delegate session is already active for this meeting.";
      case 422:
        return "Briefed mode requires text-to-speech to be configured. Try Silent instead.";
    }
  }
  return fallback;
}

function formatDelegateTs(ts?: string | null): string | null {
  if (!ts) return null;
  const d = new Date(ts);
  return isNaN(d.getTime()) ? ts : d.toLocaleString();
}

function DelegateCard({ meeting }: { meeting: Meeting }) {
  const workspaceId = meeting.workspace_id;
  const meetingId = meeting.id;
  const qc = useQueryClient();
  const [stage, setStage] = useState<DelegateStage>("silent");

  const { data: session } = useQuery({
    queryKey: ["delegate-session", workspaceId, meetingId],
    queryFn: async (): Promise<DelegateSession | null> => {
      try {
        return await delegateApi.status(workspaceId, meetingId);
      } catch (err) {
        // 404 = no delegate session has ever been started for this meeting.
        if (isAxiosError(err) && err.response?.status === 404) return null;
        throw err;
      }
    },
    retry: false,
    // Poll every 5s while a session is underway; stop once it's done or errored.
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s && s !== "done" && s !== "error" ? 5000 : false;
    },
  });

  const startMutation = useMutation({
    mutationFn: () => delegateApi.start(workspaceId, meetingId, stage),
    onSuccess: (s) => {
      toast.success(stage === "briefed" ? "Delegate is joining with your briefing." : "Delegate is joining silently.");
      qc.setQueryData(["delegate-session", workspaceId, meetingId], s);
    },
    onError: (err) => toast.error(delegateErrorMessage(err, "Couldn't start the delegate.")),
  });

  const stopMutation = useMutation({
    mutationFn: () => delegateApi.stop(workspaceId, meetingId),
    onSuccess: (s) => {
      toast.success("Delegate session stopped.");
      qc.setQueryData(["delegate-session", workspaceId, meetingId], s);
    },
    onError: (err) => toast.error(delegateErrorMessage(err, "Couldn't stop the delegate.")),
  });

  const status = session?.status;
  const sessionLive = !!status && status !== "done" && status !== "error";
  const hasConsent = meeting.proxy_consent_given;
  const followUps = (session?.follow_ups ?? []).filter((f) => f?.text);
  const disclosedAt = formatDelegateTs(session?.disclosure_logged_at);

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-white text-sm flex items-center gap-2">
          <Bot className="h-4 w-4 text-purple-400" /> Delegate
        </CardTitle>
        <CardDescription className="text-slate-400 text-sm">
          Send AmMeeting to attend this meeting on your behalf. It always discloses itself first.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stage picker */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {DELEGATE_STAGE_OPTIONS.map((opt) => {
            const selected = stage === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setStage(opt.value)}
                disabled={sessionLive || startMutation.isPending}
                className={`text-left rounded-xl border p-3 transition-colors disabled:opacity-50 ${
                  selected ? "border-purple-600 bg-purple-900/20" : "border-slate-700 bg-slate-900 hover:border-slate-500"
                }`}
              >
                <span className="flex items-center gap-2">
                  <span
                    className={`w-3.5 h-3.5 rounded-full border flex items-center justify-center flex-shrink-0 ${
                      selected ? "border-purple-400" : "border-slate-500"
                    }`}
                  >
                    {selected && <span className="w-2 h-2 rounded-full bg-purple-400" />}
                  </span>
                  <span className="text-sm font-medium text-white">{opt.label}</span>
                </span>
                <span className="block text-xs text-slate-400 mt-1">{opt.description}</span>
              </button>
            );
          })}
        </div>

        {/* Live status line */}
        {status && (
          <div className="flex items-center gap-2 text-sm flex-wrap">
            <div
              className={`w-2 h-2 rounded-full flex-shrink-0 ${
                status === "active" ? "bg-green-400 animate-pulse" :
                status === "error" ? "bg-red-400" :
                status === "done" ? "bg-slate-600" :
                "bg-blue-400 animate-pulse"
              }`}
            />
            <span className={status === "error" ? "text-red-300" : "text-slate-300"}>
              {DELEGATE_STATUS_TEXT[status] ?? `Delegate status: ${status}`}
            </span>
            {status === "done" && formatDelegateTs(session?.ended_at) && (
              <span className="text-xs text-slate-500">Ended {formatDelegateTs(session?.ended_at)}</span>
            )}
          </div>
        )}
        {status === "error" && session?.error_detail && (
          <p className="text-sm text-red-300/80">{session.error_detail}</p>
        )}

        {/* Disclosure timestamp — trust signal */}
        {disclosedAt && (
          <div className="flex items-center gap-2 text-sm text-blue-300 bg-blue-900/20 border border-blue-800 rounded-lg px-3 py-2">
            <Shield className="h-4 w-4 flex-shrink-0" />
            <span>Disclosed at {disclosedAt} — participants were told an AI delegate is present.</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 flex-wrap">
          <Button
            onClick={() => startMutation.mutate()}
            disabled={!hasConsent || sessionLive || startMutation.isPending}
            className="bg-purple-600 hover:bg-purple-700"
          >
            <Bot className="h-4 w-4 mr-2" />
            {startMutation.isPending ? "Starting…" : "Start Delegate"}
          </Button>
          {status === "active" && (
            <Button
              variant="outline"
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
              className="border-red-800 text-red-300 hover:bg-red-900/30"
            >
              {stopMutation.isPending ? "Stopping…" : "Stop Delegate"}
            </Button>
          )}
        </div>
        {!hasConsent && (
          <p className="text-orange-400 text-sm">
            Proxy consent must be enabled on this meeting before the delegate can join.
          </p>
        )}

        {/* Questions participants asked that the delegate captured for you */}
        {followUps.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <HelpCircle className="h-3.5 w-3.5" /> Questions for you
            </h4>
            <div className="space-y-2">
              {followUps.map((f, i) => (
                <div key={i} className="border border-slate-800 rounded-lg p-3">
                  <p className="text-sm text-slate-300">{f?.text}</p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    {f?.asker && <span>Asked by {f.asker}</span>}
                    {formatDelegateTs(f?.ts) && <span>{formatDelegateTs(f?.ts)}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Report Tab ─────────────────────────────────────────────────────────────────

function ReportTab({
  latestReport,
  onGenerate,
  generating,
  workspaceId,
  meetingId,
}: {
  latestReport: Report | null;
  onGenerate: () => void;
  generating: boolean;
  workspaceId: string;
  meetingId: string;
}) {
  const qc = useQueryClient();
  const [showSlackSend, setShowSlackSend] = useState(false);

  const sendSlackMutation = useMutation({
    mutationFn: () => reportApi.sendSlack(workspaceId, meetingId, latestReport!.id, "general"),
    onSuccess: () => {
      toast.success("Slack message sent! (stub)");
      setShowSlackSend(false);
      qc.invalidateQueries({ queryKey: ["reports", workspaceId, meetingId] });
    },
  });

  if (!latestReport) {
    return (
      <Card className="bg-slate-900 border-slate-800 border-dashed">
        <CardContent className="p-10 text-center">
          <FileText className="h-10 w-10 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400 mb-5">No report yet. End the meeting and generate the full report.</p>
          <Button onClick={onGenerate} disabled={generating} className="bg-blue-600 hover:bg-blue-700">
            {generating ? "Generating..." : "Generate Report"}
          </Button>
        </CardContent>
      </Card>
    );
  }

  let fullData: Record<string, unknown> = {};
  try { fullData = JSON.parse(latestReport.full_json ?? "{}"); } catch {}

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Meeting Report</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onGenerate} disabled={generating} className="border-slate-700 text-slate-300">
            <RefreshCw className="h-4 w-4 mr-2" /> Regenerate
          </Button>
          {latestReport.slack_draft && !latestReport.slack_sent && (
            <Button onClick={() => setShowSlackSend(true)} className="bg-green-700 hover:bg-green-800">
              <Send className="h-4 w-4 mr-2" /> Send to Slack
            </Button>
          )}
        </div>
      </div>

      {/* Summary */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-white text-sm">Executive Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-slate-300 leading-relaxed">{latestReport.summary}</p>
        </CardContent>
      </Card>

      {/* Action items */}
      {((fullData.action_items as unknown[] | undefined)?.length ?? 0) > 0 && (
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-sm">Action Items</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(fullData.action_items as Array<{ title: string; owner?: string; deadline?: string }>).map((ai, i) => (
                <div key={i} className="flex items-start justify-between gap-4 py-2 border-b border-slate-800 last:border-0">
                  <p className="text-sm text-slate-300">{ai.title}</p>
                  <div className="flex gap-3 flex-shrink-0 text-xs text-slate-500">
                    {ai.owner && <span className="text-blue-400">{ai.owner}</span>}
                    {ai.deadline && <span>{ai.deadline}</span>}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* R2 Delegate: what the delegate said in the meeting */}
      {((fullData.delegate_utterances as unknown[] | undefined)?.length ?? 0) > 0 && (
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-sm flex items-center gap-2">
              <Bot className="h-4 w-4 text-purple-400" /> What Your Delegate Said
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(fullData.delegate_utterances as Array<{ text?: string; ts?: string } | string>).map((u, i) => {
                const text = typeof u === "string" ? u : u?.text ?? "";
                const ts = typeof u === "string" ? null : formatDelegateTs(u?.ts);
                return (
                  <div key={i} className="flex items-start justify-between gap-4 py-2 border-b border-slate-800 last:border-0">
                    <p className="text-sm text-slate-300 italic">&quot;{text}&quot;</p>
                    {ts && <span className="text-xs text-slate-500 flex-shrink-0">{ts}</span>}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* R2 Delegate: questions participants asked that were captured for you */}
      {((fullData.delegate_follow_ups as unknown[] | undefined)?.length ?? 0) > 0 && (
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-sm flex items-center gap-2">
              <HelpCircle className="h-4 w-4 text-amber-400" /> Questions Captured For You
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(fullData.delegate_follow_ups as Array<{ asker?: string; text?: string; ts?: string } | string>).map((f, i) => {
                const text = typeof f === "string" ? f : f?.text ?? "";
                const asker = typeof f === "string" ? null : f?.asker;
                const ts = typeof f === "string" ? null : formatDelegateTs(f?.ts);
                return (
                  <div key={i} className="border border-slate-800 rounded-lg p-3">
                    <p className="text-sm text-slate-300">{text}</p>
                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                      {asker && <span>Asked by {asker}</span>}
                      {ts && <span>{ts}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Email draft */}
      {latestReport.email_draft && (
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-sm flex items-center gap-2">
              <Send className="h-4 w-4 text-cyan-400" /> Email Draft
              <Badge variant="outline" className="border-slate-700 text-slate-400 text-xs">Review before sending</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans leading-relaxed">
              {latestReport.email_draft}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Slack draft */}
      {latestReport.slack_draft && (
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-sm flex items-center gap-2">
              <Send className="h-4 w-4 text-green-400" /> Slack Draft
              {latestReport.slack_sent && <Badge className="bg-green-800 text-green-300 text-xs">Sent</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans">
              {latestReport.slack_draft}
            </pre>
          </CardContent>
        </Card>
      )}

      {showSlackSend && (
        <Card className="border-green-800 bg-green-900/20">
          <CardContent className="p-4 flex items-start justify-between gap-4">
            <p className="text-green-200 text-sm">
              Send the Slack draft to #general? This requires your review. (In MVP, this uses a stub and does not send real messages.)
            </p>
            <div className="flex gap-2 flex-shrink-0">
              <Button variant="outline" size="sm" onClick={() => setShowSlackSend(false)} className="border-slate-700">
                Cancel
              </Button>
              <Button size="sm" onClick={() => sendSlackMutation.mutate()} className="bg-green-700">
                Confirm Send
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
