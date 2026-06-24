"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { authApi } from "@/lib/api-client";
import { GoogleSignInButton } from "@/components/google-signin-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await authApi.register({ email, password, full_name: fullName });
      toast.success("Account created! Check your inbox for a verification email.");
      // Try to sign in right away; if the server requires verification first,
      // fall back to the login page.
      try {
        const tokens = await authApi.login({ email, password });
        localStorage.setItem("access_token", tokens.access_token);
        localStorage.setItem("refresh_token", tokens.refresh_token);
        router.push("/onboarding");
      } catch {
        router.push("/auth/login");
      }
    } catch (err: unknown) {
      toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Registration failed");
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
          <h1 className="text-3xl font-bold text-white">AmMeeting</h1>
          <p className="text-slate-400 mt-1">Create your account</p>
        </div>
        <Card className="border-slate-700 bg-slate-800/50 backdrop-blur">
          <CardHeader>
            <CardTitle className="text-white">Register</CardTitle>
            <CardDescription className="text-slate-400">Set up your AmMeeting account</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleRegister} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name" className="text-slate-300">Full Name</Label>
                <Input id="name" value={fullName} onChange={(e) => setFullName(e.target.value)} required className="bg-slate-700 border-slate-600 text-white" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email" className="text-slate-300">Email</Label>
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required className="bg-slate-700 border-slate-600 text-white" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password" className="text-slate-300">Password</Label>
                <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={10} className="bg-slate-700 border-slate-600 text-white" />
                <p className="text-xs text-slate-500">At least 10 characters with upper- and lowercase letters and a digit</p>
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Creating account..." : "Create account"}
              </Button>
            </form>

            <div className="my-4 flex items-center gap-3">
              <div className="h-px flex-1 bg-slate-700" />
              <span className="text-xs text-slate-500">or</span>
              <div className="h-px flex-1 bg-slate-700" />
            </div>
            <GoogleSignInButton label="Sign up with Google" />

            <p className="text-center text-sm text-slate-400 mt-4">
              Already have an account?{" "}
              <a href="/auth/login" className="text-blue-400 hover:underline">Sign in</a>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
