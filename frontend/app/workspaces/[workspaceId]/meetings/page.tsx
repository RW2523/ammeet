"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { meetingApi } from "@/lib/api-client";
import type { Meeting } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Calendar, Plus, Video, ArrowLeft, Bot } from "lucide-react";

const STATUS_STYLE: Record<string, string> = {
  draft: "bg-slate-800 text-slate-300",
  ready: "bg-blue-900 text-blue-300",
  in_progress: "bg-green-900 text-green-300 animate-pulse",
  completed: "bg-slate-800 text-slate-400",
  cancelled: "bg-red-900/40 text-red-300",
};

function fmt(dt: string | null): string {
  if (!dt) return "Not scheduled";
  const d = new Date(dt);
  return isNaN(d.getTime()) ? "Not scheduled" : d.toLocaleString();
}

export default function MeetingsListPage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;

  const { data: meetings, isLoading, isError } = useQuery({
    queryKey: ["meetings", workspaceId],
    queryFn: () => meetingApi.list(workspaceId),
  });

  return (
    <div className="p-8">
      <div className="flex items-center gap-3 mb-8">
        <Link href={`/workspaces/${workspaceId}`}>
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Calendar className="h-8 w-8 text-blue-400" /> Meetings
          </h1>
          <p className="text-slate-400 mt-1">Prepare, attend, and follow up on your meetings.</p>
        </div>
        <Link href={`/workspaces/${workspaceId}/meetings/new`}>
          <Button className="gap-2">
            <Plus className="h-4 w-4" /> New meeting
          </Button>
        </Link>
      </div>

      {isLoading && <p className="text-slate-400">Loading meetings…</p>}
      {isError && (
        <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 text-red-200">
          Couldn&apos;t load meetings. Make sure you&apos;re a member of this workspace.
        </div>
      )}

      {!isLoading && !isError && meetings?.length === 0 && (
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-10 text-center">
            <Calendar className="h-10 w-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-300 font-medium">No meetings yet</p>
            <p className="text-slate-500 text-sm mt-1 mb-4">
              Create one manually, or import from your calendar.
            </p>
            <Link href={`/workspaces/${workspaceId}/meetings/new`}>
              <Button className="gap-2">
                <Plus className="h-4 w-4" /> Create your first meeting
              </Button>
            </Link>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {meetings?.map((m: Meeting) => (
          <Link key={m.id} href={`/workspaces/${workspaceId}/meetings/${m.id}`}>
            <Card className="bg-slate-900 border-slate-800 hover:border-slate-600 transition cursor-pointer">
              <CardContent className="p-4 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-white font-semibold truncate">{m.title}</span>
                    <Badge className={`text-xs ${STATUS_STYLE[m.status] ?? "bg-slate-800 text-slate-300"}`}>
                      {m.status.replace(/_/g, " ")}
                    </Badge>
                    <Badge variant="outline" className="text-xs border-slate-700 text-slate-400 capitalize">
                      {m.mode.replace(/_/g, " ")}
                    </Badge>
                    {m.auto_join_enabled && (
                      <Badge className="text-xs bg-green-900/50 text-green-300 gap-1">
                        <Bot className="h-3 w-3" /> auto-join
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
                    <span>{fmt(m.scheduled_at)}</span>
                    {m.meeting_url && (
                      <span className="flex items-center gap-1 text-blue-400">
                        <Video className="h-3 w-3" /> join link
                      </span>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
