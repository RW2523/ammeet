"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { meetingApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { ArrowLeft, Mic, Plus } from "lucide-react";

export default function SpeakListPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.workspaceId as string;
  const [title, setTitle] = useState("");

  const { data: meetings, isLoading, refetch } = useQuery({
    queryKey: ["meetings", workspaceId],
    queryFn: () => meetingApi.list(workspaceId),
  });

  const create = useMutation({
    mutationFn: () =>
      meetingApi.create(workspaceId, { title: title.trim() || "Speak session", mode: "shadow", proxy_consent_given: true }),
    onSuccess: (m) => {
      toast.success("Session created");
      router.push(`/workspaces/${workspaceId}/speak/${m.id}`);
    },
    onError: () => toast.error("Couldn't create the session"),
  });

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href={`/workspaces/${workspaceId}`}>
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Mic className="h-8 w-8 text-green-400" /> Speak Mode
          </h1>
          <p className="text-slate-400 mt-1">Prepare your points — never miss one live.</p>
        </div>
      </div>

      <Card className="bg-slate-900 border-slate-800 mb-6">
        <CardContent className="p-4 flex items-center gap-2">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create.mutate()}
            placeholder="New session name (e.g. Sunday sermon, Client demo, Q3 review)"
            className="bg-slate-800 border-slate-700 text-white"
          />
          <Button onClick={() => create.mutate()} disabled={create.isPending} className="gap-2 shrink-0">
            <Plus className="h-4 w-4" /> New session
          </Button>
        </CardContent>
      </Card>

      {isLoading && <p className="text-slate-400">Loading…</p>}
      <div className="space-y-2">
        {meetings?.map((m) => (
          <Link key={m.id} href={`/workspaces/${workspaceId}/speak/${m.id}`}>
            <Card className="bg-slate-900 border-slate-800 hover:border-slate-600 transition cursor-pointer">
              <CardContent className="p-4 flex items-center gap-3">
                <Mic className="h-4 w-4 text-green-400 shrink-0" />
                <span className="text-white font-medium">{m.title}</span>
                <span className="text-slate-500 text-xs ml-auto capitalize">{m.status.replace(/_/g, " ")}</span>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
