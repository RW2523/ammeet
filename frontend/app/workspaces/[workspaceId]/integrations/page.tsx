"use client";

import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { integrationApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, CheckCircle, XCircle, Zap } from "lucide-react";
import Link from "next/link";

const PROVIDER_META: Record<string, { label: string; desc: string; icon: string; color: string }> = {
  jira: { label: "Jira", desc: "Sync open tickets, blockers, and assignees into meeting context.", icon: "⬡", color: "text-blue-400" },
  google_calendar: { label: "Google Calendar", desc: "Auto-import upcoming meetings, attendees, and descriptions.", icon: "📅", color: "text-green-400" },
  slack: { label: "Slack", desc: "Send meeting summaries and action items to Slack channels.", icon: "💬", color: "text-purple-400" },
  zoom: { label: "Zoom", desc: "Join Zoom meetings as proxy attendee.", icon: "🎥", color: "text-blue-300" },
  microsoft_teams: { label: "Microsoft Teams", desc: "Join Teams meetings as proxy attendee.", icon: "🟦", color: "text-indigo-400" },
  notion: { label: "Notion", desc: "Export meeting notes and action items to Notion pages.", icon: "📓", color: "text-slate-300" },
};

export default function IntegrationsPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const qc = useQueryClient();

  const { data: integrations, isLoading } = useQuery({
    queryKey: ["integrations", workspaceId],
    queryFn: () => integrationApi.list(workspaceId),
  });

  const connectMutation = useMutation({
    mutationFn: (provider: string) => integrationApi.connect(workspaceId, provider),
    onSuccess: (_, provider) => {
      qc.invalidateQueries({ queryKey: ["integrations", workspaceId] });
      toast.success(`${PROVIDER_META[provider]?.label ?? provider} connected (stub mode)`);
    },
    onError: () => toast.error("Connection failed"),
  });

  const disconnectMutation = useMutation({
    mutationFn: (provider: string) => integrationApi.disconnect(workspaceId, provider),
    onSuccess: (_, provider) => {
      qc.invalidateQueries({ queryKey: ["integrations", workspaceId] });
      toast.success(`${PROVIDER_META[provider]?.label ?? provider} disconnected`);
    },
  });

  const getStatus = (provider: string) => {
    const integ = (integrations as Array<{ provider: string; status: string }> | undefined)?.find((i) => i.provider === provider);
    return integ?.status ?? "disconnected";
  };

  return (
    <div className="p-8">
      <div className="flex items-center gap-3 mb-8">
        <Link href={`/workspaces/${workspaceId}`}>
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Zap className="h-8 w-8 text-yellow-400" /> Integrations
          </h1>
          <p className="text-slate-400 mt-1">Connect tools to enrich meeting context and automate follow-ups</p>
        </div>
      </div>

      <div className="bg-amber-900/20 border border-amber-800 rounded-xl p-4 mb-6 flex items-start gap-3">
        <span className="text-amber-400 text-lg">ℹ</span>
        <p className="text-amber-200 text-sm">
          All integrations currently run in <strong>stub/mock mode</strong>. They return realistic fixture data without requiring real OAuth credentials. 
          Real OAuth flows will be wired in Phase 2.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(PROVIDER_META).map(([provider, meta]) => {
          const status = getStatus(provider);
          const isConnected = status === "connected";
          return (
            <Card key={provider} className="bg-slate-900 border-slate-800">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{meta.icon}</span>
                    <div>
                      <CardTitle className={`text-base ${meta.color}`}>{meta.label}</CardTitle>
                      <CardDescription className="text-slate-400 text-sm mt-0.5">{meta.desc}</CardDescription>
                    </div>
                  </div>
                  {isConnected ? (
                    <Badge className="bg-green-900 text-green-300 flex items-center gap-1 text-xs">
                      <CheckCircle className="h-3 w-3" /> Connected
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="border-slate-700 text-slate-400 flex items-center gap-1 text-xs">
                      <XCircle className="h-3 w-3" /> Not connected
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                {isConnected ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-700 text-slate-400 hover:text-red-400"
                    onClick={() => disconnectMutation.mutate(provider)}
                    disabled={disconnectMutation.isPending}
                  >
                    Disconnect
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    className="bg-slate-800 hover:bg-slate-700 text-white"
                    onClick={() => connectMutation.mutate(provider)}
                    disabled={connectMutation.isPending}
                  >
                    Connect (Stub)
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
