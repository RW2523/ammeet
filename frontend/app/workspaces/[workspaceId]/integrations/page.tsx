"use client";

import { Suspense, useEffect, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { integrationApi, calendarApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, CheckCircle, XCircle, Zap } from "lucide-react";
import Link from "next/link";

const PROVIDER_META: Record<string, { label: string; desc: string; icon: string; color: string }> = {
  jira: { label: "Jira", desc: "Sync open tickets, blockers, and assignees into meeting context.", icon: "⬡", color: "text-blue-400" },
  google_calendar: { label: "Google Calendar", desc: "Connect Google to import meetings + Meet links and let the bot auto-join.", icon: "📅", color: "text-green-400" },
  slack: { label: "Slack", desc: "Send meeting summaries and action items to Slack channels.", icon: "💬", color: "text-purple-400" },
  zoom: { label: "Zoom", desc: "Join Zoom meetings as proxy attendee.", icon: "🎥", color: "text-blue-300" },
  microsoft_teams: { label: "Microsoft Teams", desc: "Connect Microsoft 365 to import Teams meetings + join links and auto-join.", icon: "🟦", color: "text-indigo-400" },
  notion: { label: "Notion", desc: "Export meeting notes and action items to Notion pages.", icon: "📓", color: "text-slate-300" },
};

interface IntegrationItem {
  id: string | null;
  provider: string;
  status: string;
  scopes: string | null;
  oauth_available: boolean;
  mode: "mock" | "oauth" | null;
}

function OAuthResultToast() {
  const searchParams = useSearchParams();
  const shown = useRef(false);

  useEffect(() => {
    if (shown.current) return;
    const result = searchParams.get("oauth");
    const provider = searchParams.get("provider");
    if (!result) return;
    shown.current = true;
    const label = provider ? PROVIDER_META[provider]?.label ?? provider : "Integration";
    if (result === "success") toast.success(`${label} connected via OAuth`);
    else if (result === "denied") toast.error(`${label} connection was denied`);
    else toast.error(`${label} connection failed — please try again`);
  }, [searchParams]);

  return null;
}

export default function IntegrationsPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const qc = useQueryClient();

  const { data: integrations, isLoading } = useQuery({
    queryKey: ["integrations", workspaceId],
    queryFn: () => integrationApi.list(workspaceId) as Promise<IntegrationItem[]>,
  });

  const connectMutation = useMutation({
    mutationFn: (provider: string) =>
      integrationApi.connect(workspaceId, provider) as Promise<{ status: string; auth_url: string | null }>,
    onSuccess: (result, provider) => {
      if (result.status === "redirect" && result.auth_url) {
        // Real OAuth — hand the browser to the provider's consent screen
        window.location.href = result.auth_url;
        return;
      }
      qc.invalidateQueries({ queryKey: ["integrations", workspaceId] });
      toast.success(`${PROVIDER_META[provider]?.label ?? provider} connected (mock mode)`);
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

  const syncMutation = useMutation({
    mutationFn: () => calendarApi.syncAutoJoin(workspaceId, true),
    onSuccess: (r) =>
      toast.success(
        r.created > 0
          ? `${r.created} meeting(s) scheduled for auto-join (scanned ${r.scanned})`
          : `Calendar synced — no new meetings with join links (scanned ${r.scanned})`
      ),
    onError: () => toast.error("Calendar sync failed"),
  });

  const CALENDAR_PROVIDERS = ["google_calendar", "microsoft_teams"];

  const getIntegration = (provider: string) =>
    integrations?.find((i) => i.provider === provider);

  const anyOauthAvailable = integrations?.some((i) => i.oauth_available) ?? false;

  return (
    <div className="p-8">
      <Suspense fallback={null}>
        <OAuthResultToast />
      </Suspense>
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

      {!isLoading && !anyOauthAvailable && (
        <div className="bg-amber-900/20 border border-amber-800 rounded-xl p-4 mb-6 flex items-start gap-3">
          <span className="text-amber-400 text-lg">ℹ</span>
          <p className="text-amber-200 text-sm">
            No OAuth credentials are configured on this server, so integrations connect in{" "}
            <strong>mock mode</strong> with realistic fixture data. Set{" "}
            <code className="text-amber-100">GOOGLE_CLIENT_ID</code>,{" "}
            <code className="text-amber-100">SLACK_CLIENT_ID</code>, or{" "}
            <code className="text-amber-100">JIRA_CLIENT_ID</code> (and secrets) in the backend{" "}
            <code className="text-amber-100">.env</code> to enable real OAuth connections.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(PROVIDER_META).map(([provider, meta]) => {
          const integration = getIntegration(provider);
          const isConnected = integration?.status === "connected";
          const mode = integration?.mode;
          const oauthAvailable = integration?.oauth_available ?? false;
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
                  <div className="flex flex-col items-end gap-1">
                    {isConnected ? (
                      <Badge className="bg-green-900 text-green-300 flex items-center gap-1 text-xs">
                        <CheckCircle className="h-3 w-3" /> Connected
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-slate-700 text-slate-400 flex items-center gap-1 text-xs">
                        <XCircle className="h-3 w-3" /> Not connected
                      </Badge>
                    )}
                    {isConnected && mode && (
                      <Badge variant="outline" className={`text-xs ${mode === "oauth" ? "border-blue-700 text-blue-300" : "border-amber-800 text-amber-300"}`}>
                        {mode === "oauth" ? "OAuth" : "Mock data"}
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                {isConnected ? (
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-slate-700 text-slate-400 hover:text-red-400"
                      onClick={() => disconnectMutation.mutate(provider)}
                      disabled={disconnectMutation.isPending}
                    >
                      Disconnect
                    </Button>
                    {CALENDAR_PROVIDERS.includes(provider) && (
                      <Button
                        size="sm"
                        className="bg-green-700 hover:bg-green-600 text-white"
                        onClick={() => syncMutation.mutate()}
                        disabled={syncMutation.isPending}
                        title="Scan your calendar for meetings with join links and schedule the bot to auto-join"
                      >
                        {syncMutation.isPending ? "Syncing…" : "Sync & auto-join"}
                      </Button>
                    )}
                  </div>
                ) : (
                  <Button
                    size="sm"
                    className={oauthAvailable ? "bg-blue-600 hover:bg-blue-500 text-white" : "bg-slate-800 hover:bg-slate-700 text-white"}
                    onClick={() => connectMutation.mutate(provider)}
                    disabled={connectMutation.isPending}
                  >
                    {oauthAvailable ? "Connect with OAuth" : "Connect (mock)"}
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
