"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Bot, Brain, CheckCircle, FileText, MessageSquare, Shield, Sparkles, Zap } from "lucide-react";

const FEATURES = [
  {
    icon: Brain,
    title: "Knows what to ask",
    desc: "Reads previous transcripts, Jira tickets, and project context, then generates smart, categorized questions before every meeting.",
    color: "text-blue-400",
  },
  {
    icon: Bot,
    title: "Attends as your transparent proxy",
    desc: "Introduces itself openly, asks only your approved questions, answers from your knowledge base, and never makes commitments for you.",
    color: "text-purple-400",
  },
  {
    icon: Shield,
    title: "Escalates what matters",
    desc: "Budget, legal, contract, and HR topics are intercepted and escalated to you — the AI never decides on restricted matters.",
    color: "text-green-400",
  },
  {
    icon: FileText,
    title: "Reports that write themselves",
    desc: "Structured post-meeting reports with decisions, action items, and risks — plus ready-to-send Slack, email, and Jira drafts.",
    color: "text-amber-400",
  },
  {
    icon: MessageSquare,
    title: "A memory of every meeting",
    desc: "A searchable knowledge base across all your meetings. Ask anything; get answers grounded in what was actually said.",
    color: "text-cyan-400",
  },
  {
    icon: Zap,
    title: "Connected to your tools",
    desc: "Google Calendar, Slack, and Jira integrations bring context in and push results out — with your review on every external action.",
    color: "text-pink-400",
  },
];

const PLANS = [
  {
    name: "Free",
    price: "$0",
    desc: "Try the full workflow",
    features: ["3 proxy sessions / month", "10 AI question batches / month", "10 reports / month", "Knowledge base search"],
    cta: "Start free",
    highlight: false,
  },
  {
    name: "Pro",
    price: "$29",
    desc: "For people who live in meetings",
    features: ["50 proxy sessions / month", "200 AI question batches / month", "200 reports / month", "Calendar, Slack & Jira integrations"],
    cta: "Start with Pro",
    highlight: true,
  },
  {
    name: "Team",
    price: "$99",
    desc: "For whole teams and orgs",
    features: ["Unlimited proxy sessions", "Unlimited AI questions & reports", "All integrations", "Priority support"],
    cta: "Start with Team",
    highlight: false,
  },
];

export default function LandingPage() {
  const [loggedIn, setLoggedIn] = useState(false);

  useEffect(() => {
    // localStorage is only available post-mount; reading it here (not during
    // render) avoids an SSR/client hydration mismatch on the nav buttons.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoggedIn(Boolean(localStorage.getItem("access_token")));
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Nav */}
      <nav className="max-w-6xl mx-auto flex items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center font-bold">AM</div>
          <span className="text-lg font-semibold">AmMeeting</span>
        </div>
        <div className="flex items-center gap-3">
          {loggedIn ? (
            <Link href="/dashboard">
              <Button className="bg-blue-600 hover:bg-blue-500">Open dashboard</Button>
            </Link>
          ) : (
            <>
              <Link href="/auth/login">
                <Button variant="ghost" className="text-slate-300 hover:text-white">Sign in</Button>
              </Link>
              <Link href="/auth/register">
                <Button className="bg-blue-600 hover:bg-blue-500">Get started</Button>
              </Link>
            </>
          )}
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-4xl mx-auto text-center px-6 pt-20 pb-16">
        <Badge className="bg-blue-900/60 text-blue-300 mb-6 inline-flex items-center gap-1">
          <Sparkles className="h-3 w-3" /> The transparent AI proxy attender
        </Badge>
        <h1 className="text-5xl md:text-6xl font-bold leading-tight">
          Send AI to your next meeting.
          <span className="block text-blue-400">It knows what to ask.</span>
        </h1>
        <p className="text-slate-400 text-lg mt-6 max-w-2xl mx-auto">
          AmMeeting preps your questions, attends with full disclosure, collects the answers,
          escalates anything sensitive to you, and delivers the report — so work keeps moving
          even when you can&apos;t be there.
        </p>
        <div className="flex items-center justify-center gap-4 mt-8">
          <Link href="/auth/register">
            <Button size="lg" className="bg-blue-600 hover:bg-blue-500 text-lg px-8">Try it free</Button>
          </Link>
          <Link href="/auth/login">
            <Button size="lg" variant="outline" className="border-slate-700 text-slate-300 hover:text-white text-lg px-8">
              Sign in
            </Button>
          </Link>
        </div>
        <p className="text-slate-500 text-sm mt-4">Free plan included — no credit card required</p>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <h2 className="text-3xl font-bold text-center mb-12">Not a notetaker. A participant with guardrails.</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map((f) => (
            <Card key={f.title} className="bg-slate-900/70 border-slate-800">
              <CardHeader className="pb-2">
                <f.icon className={`h-8 w-8 ${f.color} mb-2`} />
                <CardTitle className="text-white text-lg">{f.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-slate-400 text-sm">{f.desc}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <h2 className="text-3xl font-bold text-center mb-2">Simple pricing</h2>
        <p className="text-slate-400 text-center mb-12">Per workspace, per month. Upgrade or cancel anytime.</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((plan) => (
            <Card
              key={plan.name}
              className={`bg-slate-900/70 ${plan.highlight ? "border-blue-600 ring-1 ring-blue-600" : "border-slate-800"}`}
            >
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-white">{plan.name}</CardTitle>
                  {plan.highlight && <Badge className="bg-blue-600 text-white">Popular</Badge>}
                </div>
                <div className="mt-2">
                  <span className="text-4xl font-bold">{plan.price}</span>
                  <span className="text-slate-400">/mo</span>
                </div>
                <p className="text-slate-400 text-sm">{plan.desc}</p>
              </CardHeader>
              <CardContent className="space-y-3">
                {plan.features.map((feat) => (
                  <div key={feat} className="flex items-center gap-2 text-sm text-slate-300">
                    <CheckCircle className="h-4 w-4 text-green-400 shrink-0" /> {feat}
                  </div>
                ))}
                <Link href="/auth/register" className="block pt-3">
                  <Button className={`w-full ${plan.highlight ? "bg-blue-600 hover:bg-blue-500" : "bg-slate-800 hover:bg-slate-700"}`}>
                    {plan.cta}
                  </Button>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Trust */}
      <section className="max-w-4xl mx-auto px-6 py-16 text-center">
        <h2 className="text-2xl font-bold mb-6">Built for trust from day one</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm text-slate-400">
          <div><Shield className="h-6 w-6 text-green-400 mx-auto mb-2" />Mandatory disclosure — the proxy always introduces itself before speaking.</div>
          <div><Shield className="h-6 w-6 text-green-400 mx-auto mb-2" />Workspace-isolated knowledge with full audit logging and retention controls.</div>
          <div><Shield className="h-6 w-6 text-green-400 mx-auto mb-2" />No external action — Slack, email, Jira — without your explicit review.</div>
        </div>
      </section>

      <footer className="border-t border-slate-800 py-8 text-center text-slate-500 text-sm">
        © {new Date().getFullYear()} AmMeeting — The AI meeting assistant that knows what to ask.
      </footer>
    </div>
  );
}
