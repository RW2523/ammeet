"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { workspaceApi, meetingApi } from "@/lib/api-client";
import { useWorkspaceStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar, Users, Plus, ArrowRight, Zap } from "lucide-react";
import Link from "next/link";

const MODE_LABELS: Record<string, string> = {
  shadow: "Shadow",
  live_navigator: "Live Navigator",
  proxy: "Proxy",
  data_collection: "Data Collection",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-slate-700 text-slate-300",
  ready: "bg-blue-900 text-blue-300",
  in_progress: "bg-green-900 text-green-300",
  completed: "bg-slate-800 text-slate-400",
  cancelled: "bg-red-900 text-red-300",
};

export default function WorkspacePage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const router = useRouter();
  const { setCurrent } = useWorkspaceStore();

  const { data: workspace } = useQuery({
    queryKey: ["workspace", workspaceId],
    queryFn: () => workspaceApi.get(workspaceId),
  });

  const { data: meetings, isLoading } = useQuery({
    queryKey: ["meetings", workspaceId],
    queryFn: () => meetingApi.list(workspaceId),
  });

  useEffect(() => {
    if (workspace) setCurrent(workspace);
  }, [workspace, setCurrent]);

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">{workspace?.name ?? "Loading..."}</h1>
          <p className="text-slate-400 mt-1">{workspace?.description ?? ""}</p>
        </div>
        <div className="flex gap-3">
          <Link href={`/workspaces/${workspaceId}/people`}>
            <Button variant="outline" className="border-slate-700 text-slate-300">
              <Users className="h-4 w-4 mr-2" /> People
            </Button>
          </Link>
          <Link href={`/workspaces/${workspaceId}/meetings/new`}>
            <Button>
              <Plus className="h-4 w-4 mr-2" /> New Meeting
            </Button>
          </Link>
        </div>
      </div>

      {/* Meetings */}
      <div>
        <h2 className="text-xl font-semibold text-white mb-4">Meetings</h2>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="bg-slate-900 border-slate-800 animate-pulse h-20" />
            ))}
          </div>
        ) : meetings?.length === 0 ? (
          <Card className="bg-slate-900 border-slate-800 border-dashed">
            <CardContent className="p-10 text-center">
              <Calendar className="h-10 w-10 text-slate-600 mx-auto mb-3" />
              <h3 className="text-white font-semibold mb-2">No meetings yet</h3>
              <p className="text-slate-400 text-sm mb-5">
                Create a meeting, upload context, generate questions, and run a proxy session.
              </p>
              <Link href={`/workspaces/${workspaceId}/meetings/new`}>
                <Button>Create First Meeting</Button>
              </Link>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {meetings?.map((m) => (
              <Card
                key={m.id}
                className="bg-slate-900 border-slate-800 hover:border-slate-700 cursor-pointer transition-colors group"
                onClick={() => router.push(`/workspaces/${workspaceId}/meetings/${m.id}`)}
              >
                <CardContent className="p-5 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`w-2 h-10 rounded-full ${m.status === "in_progress" ? "bg-green-500" : m.status === "completed" ? "bg-slate-600" : "bg-blue-500"}`} />
                    <div>
                      <p className="text-white font-medium">{m.title}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[m.status]}`}>
                          {m.status.replace("_", " ")}
                        </span>
                        <span className="text-xs text-slate-500">{MODE_LABELS[m.mode]}</span>
                        {m.mode === "proxy" && (
                          <span className="text-xs flex items-center gap-1 text-purple-400">
                            <Zap className="h-3 w-3" /> Proxy enabled
                          </span>
                        )}
                        {m.scheduled_at && (
                          <span className="text-xs text-slate-500">
                            {new Date(m.scheduled_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-slate-600 group-hover:text-slate-300 transition-colors" />
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
