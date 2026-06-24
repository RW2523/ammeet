"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { authApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      toast.error("Passwords do not match");
      return;
    }
    setLoading(true);
    try {
      await authApi.resetPassword(token, password);
      toast.success("Password reset. You can sign in now.");
      router.push("/auth/login");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg || "Reset failed — the link may have expired.");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <CardContent className="pt-6 text-center space-y-3">
        <p className="text-white">This reset link is invalid.</p>
        <Link href="/auth/forgot-password" className="text-blue-400 hover:underline text-sm">
          Request a new one
        </Link>
      </CardContent>
    );
  }

  return (
    <>
      <CardHeader>
        <CardTitle className="text-white">Choose a new password</CardTitle>
        <CardDescription className="text-slate-400">
          At least 10 characters with upper- and lowercase letters and a digit
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="password" className="text-slate-300">New password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm" className="text-slate-300">Confirm password</Label>
            <Input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              className="bg-slate-700 border-slate-600 text-white"
            />
          </div>
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Resetting..." : "Reset password"}
          </Button>
        </form>
      </CardContent>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-800 p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-blue-600 mb-4">
            <span className="text-white text-2xl font-bold">AM</span>
          </div>
          <h1 className="text-3xl font-bold text-white">Reset your password</h1>
        </div>
        <Card className="border-slate-700 bg-slate-800/50 backdrop-blur">
          <Suspense fallback={<CardContent className="pt-6 text-slate-400 text-center">Loading…</CardContent>}>
            <ResetPasswordForm />
          </Suspense>
        </Card>
      </div>
    </div>
  );
}
