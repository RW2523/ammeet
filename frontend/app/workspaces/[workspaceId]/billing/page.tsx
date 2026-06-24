"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import Link from "next/link";
import { billingApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ArrowLeft, CreditCard, Sparkles } from "lucide-react";

const METRIC_LABELS: Record<string, string> = {
  proxy_sessions: "Proxy sessions",
  ai_question_batches: "AI question batches",
  report_generations: "Report generations",
};

const PLAN_LABELS: Record<string, { name: string; desc: string }> = {
  free: { name: "Free", desc: "Try the full workflow" },
  pro: { name: "Pro", desc: "For people who live in meetings" },
  team: { name: "Team", desc: "For whole teams and orgs" },
};

export default function BillingPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const qc = useQueryClient();

  const { data: billing, isLoading } = useQuery({
    queryKey: ["billing", workspaceId],
    queryFn: () => billingApi.get(workspaceId),
  });

  const checkoutMutation = useMutation({
    mutationFn: (plan: string) => billingApi.checkout(workspaceId, plan),
    onSuccess: (result) => {
      if (result.mock) {
        qc.invalidateQueries({ queryKey: ["billing", workspaceId] });
        toast.success(`Plan changed to ${result.plan} (mock billing — no Stripe configured)`);
      } else if (result.checkout_url) {
        window.location.href = result.checkout_url;
      }
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg || "Could not start checkout");
    },
  });

  const portalMutation = useMutation({
    mutationFn: () => billingApi.portal(workspaceId),
    onSuccess: (result) => {
      window.location.href = result.portal_url;
    },
    onError: () => toast.error("Could not open billing portal"),
  });

  if (isLoading || !billing) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-slate-800 rounded w-1/3" />
          <div className="h-40 bg-slate-800 rounded" />
        </div>
      </div>
    );
  }

  const currentPlan = PLAN_LABELS[billing.plan] ?? PLAN_LABELS.free;

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center gap-3 mb-8">
        <Link href={`/workspaces/${workspaceId}`}>
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <CreditCard className="h-8 w-8 text-green-400" /> Plan &amp; Billing
          </h1>
          <p className="text-slate-400 mt-1">Manage this workspace&apos;s subscription and usage</p>
        </div>
      </div>

      {/* Current plan + usage */}
      <Card className="bg-slate-900 border-slate-800 mb-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-white">
                {currentPlan.name} plan
                {billing.subscription_status && (
                  <Badge className="ml-3 bg-green-900 text-green-300 text-xs">{billing.subscription_status}</Badge>
                )}
              </CardTitle>
              <CardDescription className="text-slate-400">{currentPlan.desc}</CardDescription>
            </div>
            {billing.billing_enabled && billing.plan !== "free" && (
              <Button
                variant="outline"
                className="border-slate-700 text-slate-300"
                onClick={() => portalMutation.mutate()}
                disabled={portalMutation.isPending}
              >
                Manage subscription
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(billing.usage).map(([metric, { used, limit }]) => (
            <div key={metric}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-300">{METRIC_LABELS[metric] ?? metric}</span>
                <span className="text-slate-400">
                  {used} / {limit === null ? "unlimited" : limit} this month
                </span>
              </div>
              <Progress
                value={limit === null ? 5 : Math.min(100, (used / limit) * 100)}
                className="h-2 bg-slate-800"
              />
            </div>
          ))}
          {billing.current_period_end && (
            <p className="text-xs text-slate-500">
              Current period ends {new Date(billing.current_period_end).toLocaleDateString()}
            </p>
          )}
          {!billing.billing_enabled && (
            <p className="text-xs text-amber-400">
              Mock billing mode — Stripe is not configured on this server, plan changes apply instantly.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Upgrade options */}
      <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-blue-400" /> Plans
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {billing.plans.map((plan) => {
          const label = PLAN_LABELS[plan.id] ?? { name: plan.id, desc: "" };
          const isCurrent = plan.id === billing.plan;
          return (
            <Card key={plan.id} className={`bg-slate-900 ${isCurrent ? "border-blue-600" : "border-slate-800"}`}>
              <CardHeader>
                <CardTitle className="text-white flex items-center justify-between">
                  {label.name}
                  {isCurrent && <Badge className="bg-blue-900 text-blue-300 text-xs">Current</Badge>}
                </CardTitle>
                <div>
                  <span className="text-3xl font-bold text-white">${plan.price_usd_monthly}</span>
                  <span className="text-slate-400">/mo</span>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(plan.limits).map(([metric, limit]) => (
                  <p key={metric} className="text-sm text-slate-400">
                    {limit === null ? "Unlimited" : limit} {METRIC_LABELS[metric]?.toLowerCase() ?? metric}
                  </p>
                ))}
                {!isCurrent && plan.id !== "free" && (
                  <Button
                    className="w-full mt-3 bg-blue-600 hover:bg-blue-500"
                    onClick={() => checkoutMutation.mutate(plan.id)}
                    disabled={checkoutMutation.isPending}
                  >
                    {checkoutMutation.isPending ? "Redirecting..." : `Upgrade to ${label.name}`}
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
