"use client";

import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store";
import { Sidebar } from "@/components/sidebar";
import { useEffect } from "react";

export default function WorkspacesLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user } = useAuthStore();

  useEffect(() => {
    if (!user && !localStorage.getItem("access_token")) {
      router.push("/auth/login");
    }
  }, [user, router]);

  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 ml-64 min-h-screen bg-slate-950 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
