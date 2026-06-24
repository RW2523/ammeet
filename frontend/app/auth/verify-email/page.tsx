"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { authApi } from "@/lib/api-client";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CheckCircle, Loader2, XCircle } from "lucide-react";

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  // Derive the initial state from the token so the no-token case doesn't need a
  // synchronous setState inside the effect.
  const [state, setState] = useState<"verifying" | "success" | "error">(token ? "verifying" : "error");
  const requested = useRef(false);

  useEffect(() => {
    if (!token || requested.current) return;
    requested.current = true;
    authApi
      .verifyEmail(token)
      .then(() => setState("success"))
      .catch(() => setState("error"));
  }, [token]);

  return (
    <CardContent className="pt-6 text-center space-y-4">
      {state === "verifying" && (
        <>
          <Loader2 className="h-12 w-12 text-blue-400 mx-auto animate-spin" />
          <p className="text-white">Verifying your email…</p>
        </>
      )}
      {state === "success" && (
        <>
          <CheckCircle className="h-12 w-12 text-green-400 mx-auto" />
          <p className="text-white font-medium">Email verified!</p>
          <p className="text-slate-400 text-sm">Your account is ready to use.</p>
          <Link href="/auth/login">
            <Button className="mt-2">Sign in</Button>
          </Link>
        </>
      )}
      {state === "error" && (
        <>
          <XCircle className="h-12 w-12 text-red-400 mx-auto" />
          <p className="text-white font-medium">Verification failed</p>
          <p className="text-slate-400 text-sm">
            The link is invalid or has expired. Sign in to request a new verification email.
          </p>
          <Link href="/auth/login">
            <Button variant="outline" className="border-slate-700 text-slate-300 mt-2">Back to sign in</Button>
          </Link>
        </>
      )}
    </CardContent>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-800 p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600 mb-4">
            <span className="text-white text-2xl font-bold">AM</span>
          </div>
          <h1 className="text-3xl font-bold text-white">AmMeeting</h1>
        </div>
        <Card className="border-slate-700 bg-slate-800/50 backdrop-blur">
          <Suspense fallback={<CardContent className="pt-6 text-slate-400 text-center">Loading…</CardContent>}>
            <VerifyEmailInner />
          </Suspense>
        </Card>
      </div>
    </div>
  );
}
