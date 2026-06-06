"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { authApi, workspaceApi } from "@/lib/api-client";
import { useAuthStore, useWorkspaceStore } from "@/lib/store";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Calendar, Users, MessageSquare, Zap, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  const router = useRouter();
  const { user, setAuth } = useAuthStore();
  const { setCurrent } = useWorkspaceStore();

  const { data: workspaces, isLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: workspaceApi.list,
  });

  useEffect(() => {
    if (!localStorage.getItem("access_token")) {
      router.push("/auth/login");
      return;
    }
    if (!user) {
      authApi.me().then((u) => {
        setAuth(u, localStorage.getItem("access_token") || "", localStorage.getItem("refresh_token") || "");
      }).catch(() => router.push("/auth/login"));
    }
  }, [user, router, setAuth]);

  const stats = [
    { label: "Workspaces", value: workspaces?.length ?? 0, icon: Users, color: "text-blue-400" },
    { label: "Meetings Today", value: 0, icon: Calendar, color: "text-green-400" },
    { label: "Open Actions", value: 0, icon: MessageSquare, color: "text-amber-400" },
    { label: "AI Sessions", value: 0, icon: Zap, color: "text-purple-400" },
  ];

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">
          Welcome back, {user?.full_name?.split(" ")[0] ?? "there"} 👋
        </h1>
        <p className="text-slate-400 mt-1">
          Your AI meeting assistant is ready. Prepare smarter, ask better, follow up faster.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((stat) => (
          <Card key={stat.label} className="bg-slate-900 border-slate-800">
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-slate-400">{stat.label}</p>
                  <p className="text-2xl font-bold text-white mt-1">{stat.value}</p>
                </div>
                <stat.icon className={`h-8 w-8 ${stat.color}`} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Workspaces */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Your Workspaces</h2>
          <Link href="/workspaces">
            <Button variant="outline" size="sm" className="border-slate-700 text-slate-300">
              View all <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          </Link>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="bg-slate-900 border-slate-800 animate-pulse">
                <CardContent className="p-6 h-32" />
              </Card>
            ))}
          </div>
        ) : workspaces?.length === 0 ? (
          <Card className="bg-slate-900 border-slate-800 border-dashed">
            <CardContent className="p-8 text-center">
              <p className="text-slate-400 mb-4">No workspaces yet. Create your first one to get started.</p>
              <Link href="/workspaces">
                <Button>Create Workspace</Button>
              </Link>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workspaces?.map((ws) => (
              <Card
                key={ws.id}
                className="bg-slate-900 border-slate-800 hover:border-blue-600 cursor-pointer transition-colors"
                onClick={() => {
                  setCurrent(ws);
                  router.push(`/workspaces/${ws.id}`);
                }}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div className="w-10 h-10 rounded-xl bg-blue-900 flex items-center justify-center">
                      <span className="text-blue-300 font-bold text-sm">
                        {ws.name.charAt(0)}
                      </span>
                    </div>
                    <Badge variant="secondary" className="text-xs">Active</Badge>
                  </div>
                  <CardTitle className="text-white text-base mt-3">{ws.name}</CardTitle>
                  <CardDescription className="text-slate-400 text-sm line-clamp-2">
                    {ws.description ?? "No description"}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="flex items-center gap-1 text-xs text-slate-500">
                    <Calendar className="h-3 w-3" />
                    Created {new Date(ws.created_at).toLocaleDateString()}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <Card className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 border-blue-800/30">
        <CardHeader>
          <CardTitle className="text-white">Quick Start</CardTitle>
          <CardDescription className="text-slate-400">
            Run the demo proxy session to see AmMeeting in action
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Link href="/workspaces">
              <Button variant="outline" className="w-full border-slate-700 text-slate-300 hover:text-white">
                Create Workspace
              </Button>
            </Link>
            <Link href="/workspaces">
              <Button variant="outline" className="w-full border-slate-700 text-slate-300 hover:text-white">
                Upload Meeting Context
              </Button>
            </Link>
            <Link href="/workspaces">
              <Button className="w-full bg-blue-600 hover:bg-blue-700">
                <Zap className="h-4 w-4 mr-2" />
                Start Proxy Session
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
