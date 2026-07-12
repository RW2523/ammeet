"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { BASE_URL } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, XCircle, Mic } from "lucide-react";

interface PublicRecap {
  title: string;
  summary: string;
  mode?: string | null;
  covered: string[];
  missed: string[];
  action_items: { title: string; owner?: string | null }[];
  follow_ups: string[];
  responses: { speaker: string; text: string; kind: string }[];
  shared_at?: string | null;
}

export default function PublicRecapPage() {
  const token = useParams().token as string;
  const [recap, setRecap] = useState<PublicRecap | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE_URL}/api/public/reports/${token}`)
      .then(async (r) => {
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "This recap link is invalid or was revoked.");
        return r.json();
      })
      .then(setRecap)
      .catch((e) => setError(e.message));
  }, [token]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      <nav className="max-w-3xl mx-auto flex items-center justify-between px-6 py-5">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center font-bold text-sm">AM</div>
          <span className="font-semibold">AmMeeting</span>
        </Link>
        <Link href="/auth/register" className="text-sm text-slate-400 hover:text-white">Try it free →</Link>
      </nav>

      <main className="max-w-3xl mx-auto px-6 pb-20">
        {error && (
          <Card className="bg-slate-900 border-slate-800 mt-10">
            <CardContent className="p-8 text-center text-slate-400">{error}</CardContent>
          </Card>
        )}

        {!error && !recap && (
          <p className="text-slate-500 mt-10 text-center">Loading recap…</p>
        )}

        {recap && (
          <div className="mt-6 space-y-5">
            <div>
              <p className="inline-flex items-center gap-1.5 text-xs text-green-400 mb-2">
                <Mic className="h-3.5 w-3.5" /> Speaking recap
              </p>
              <h1 className="text-3xl font-bold">{recap.title}</h1>
            </div>

            {recap.summary && (
              <Card className="bg-slate-900 border-slate-800">
                <CardContent className="p-5 text-slate-200 leading-relaxed">{recap.summary}</CardContent>
              </Card>
            )}

            {(recap.covered.length > 0 || recap.missed.length > 0) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card className="bg-slate-900 border-slate-800">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm text-green-400 flex items-center gap-1.5">
                      <CheckCircle2 className="h-4 w-4" /> Covered ({recap.covered.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1.5">
                    {recap.covered.map((c, i) => (
                      <p key={i} className="text-sm text-slate-300">• {c}</p>
                    ))}
                    {recap.covered.length === 0 && <p className="text-sm text-slate-600">—</p>}
                  </CardContent>
                </Card>
                <Card className="bg-slate-900 border-slate-800">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm text-red-400 flex items-center gap-1.5">
                      <XCircle className="h-4 w-4" /> Missed ({recap.missed.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1.5">
                    {recap.missed.map((m, i) => (
                      <p key={i} className="text-sm text-slate-300">• {m}</p>
                    ))}
                    {recap.missed.length === 0 && <p className="text-sm text-slate-600">Nothing missed 🎉</p>}
                  </CardContent>
                </Card>
              </div>
            )}

            {recap.action_items.length > 0 && (
              <Card className="bg-slate-900 border-slate-800">
                <CardHeader className="pb-2"><CardTitle className="text-sm text-white">Action items</CardTitle></CardHeader>
                <CardContent className="space-y-1">
                  {recap.action_items.map((a, i) => (
                    <p key={i} className="text-sm text-slate-300">• {a.title}{a.owner ? ` — ${a.owner}` : ""}</p>
                  ))}
                </CardContent>
              </Card>
            )}

            {recap.responses.length > 0 && (
              <Card className="bg-slate-900 border-slate-800">
                <CardHeader className="pb-2"><CardTitle className="text-sm text-white">Audience responses</CardTitle></CardHeader>
                <CardContent className="space-y-1">
                  {recap.responses.map((r, i) => (
                    <p key={i} className="text-sm text-slate-300">
                      <span className="text-slate-500">{r.kind} · {r.speaker}:</span> {r.text}
                    </p>
                  ))}
                </CardContent>
              </Card>
            )}

            {recap.follow_ups.length > 0 && (
              <Card className="bg-slate-900 border-slate-800">
                <CardHeader className="pb-2"><CardTitle className="text-sm text-white">Follow-ups</CardTitle></CardHeader>
                <CardContent className="space-y-1">
                  {recap.follow_ups.map((f, i) => (
                    <p key={i} className="text-sm text-slate-300">• {f}</p>
                  ))}
                </CardContent>
              </Card>
            )}

            <p className="text-center text-xs text-slate-600 pt-4">
              Recapped with{" "}
              <Link href="/" className="text-slate-400 hover:text-white">AmMeeting</Link>{" "}
              — never miss a point again.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
