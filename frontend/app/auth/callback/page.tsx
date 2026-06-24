"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api-client";
import { useAuthStore } from "@/lib/store";

/**
 * Landing page for the Google OIDC redirect. The backend appends the issued JWTs to
 * the URL fragment (#access_token=...&refresh_token=...) so they never hit the server
 * or Referer header. We read them here, hydrate the auth store, and continue.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");
    // Scrub the JWTs from the address bar immediately, before any async work.
    window.history.replaceState(null, "", window.location.pathname);
    if (!access || !refresh) {
      router.replace("/auth/login?error=google_failed");
      return;
    }
    // me() authenticates via the token in localStorage; set it, but roll back if the
    // session can't be confirmed so we never leave orphan tokens behind.
    localStorage.setItem("access_token", access);
    localStorage.setItem("refresh_token", refresh);
    authApi
      .me()
      .then((user) => {
        setAuth(user, access, refresh);
        router.replace("/dashboard");
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        router.replace("/auth/login?error=google_failed");
      });
  }, [router, setAuth]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 to-slate-800 text-slate-300">
      <div className="flex items-center gap-3">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-500 border-t-blue-400" />
        Signing you in…
      </div>
    </div>
  );
}
