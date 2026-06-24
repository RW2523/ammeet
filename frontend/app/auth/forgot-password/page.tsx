"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { authApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { MailCheck } from "lucide-react";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await authApi.forgotPassword(email);
      setSent(true);
    } catch {
      toast.error("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

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
          {sent ? (
            <CardContent className="pt-6 text-center space-y-4">
              <MailCheck className="h-12 w-12 text-green-400 mx-auto" />
              <p className="text-white font-medium">Check your inbox</p>
              <p className="text-slate-400 text-sm">
                If an account exists for <span className="text-slate-200">{email}</span>, we sent a
                password reset link. It expires in 1 hour.
              </p>
              <Link href="/auth/login" className="text-blue-400 hover:underline text-sm block">
                Back to sign in
              </Link>
            </CardContent>
          ) : (
            <>
              <CardHeader>
                <CardTitle className="text-white">Forgot password</CardTitle>
                <CardDescription className="text-slate-400">
                  Enter your email and we&apos;ll send you a reset link
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email" className="text-slate-300">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@company.com"
                      required
                      className="bg-slate-700 border-slate-600 text-white placeholder:text-slate-500"
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={loading}>
                    {loading ? "Sending..." : "Send reset link"}
                  </Button>
                </form>
                <p className="text-center text-sm text-slate-400 mt-4">
                  Remembered it?{" "}
                  <Link href="/auth/login" className="text-blue-400 hover:underline">Sign in</Link>
                </p>
              </CardContent>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
