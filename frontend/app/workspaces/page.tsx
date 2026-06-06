"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { workspaceApi } from "@/lib/api-client";
import { useWorkspaceStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Plus, ArrowRight, Calendar } from "lucide-react";

export default function WorkspacesPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const { setCurrent } = useWorkspaceStore();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const { data: workspaces, isLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: workspaceApi.list,
  });

  const createMutation = useMutation({
    mutationFn: () => workspaceApi.create({ name, description: description || undefined }),
    onSuccess: (ws) => {
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      toast.success("Workspace created!");
      setCurrent(ws);
      setShowCreate(false);
      router.push(`/workspaces/${ws.id}`);
    },
    onError: () => toast.error("Failed to create workspace"),
  });

  const goToWorkspace = (ws: import("@/lib/types").Workspace) => {
    setCurrent(ws);
    router.push(`/workspaces/${ws.id}`);
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Workspaces</h1>
          <p className="text-slate-400 mt-1">Organize your meetings by project, client, or team</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-2" /> New Workspace
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="bg-slate-900 border-slate-800 animate-pulse h-44" />
          ))}
        </div>
      ) : workspaces?.length === 0 ? (
        <Card className="bg-slate-900 border-slate-800 border-dashed">
          <CardContent className="p-12 text-center">
            <div className="w-16 h-16 rounded-2xl bg-slate-800 flex items-center justify-center mx-auto mb-4">
              <Plus className="h-8 w-8 text-slate-500" />
            </div>
            <h3 className="text-white font-semibold text-lg mb-2">Create your first workspace</h3>
            <p className="text-slate-400 mb-6 max-w-sm mx-auto">
              A workspace represents a project, client, or team. Add context, people, and meetings to get started.
            </p>
            <Button onClick={() => setShowCreate(true)}>Create Workspace</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workspaces?.map((ws) => (
            <Card
              key={ws.id}
              className="bg-slate-900 border-slate-800 hover:border-blue-600 cursor-pointer transition-all hover:shadow-lg hover:shadow-blue-900/20 group"
              onClick={() => goToWorkspace(ws)}
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div className="w-11 h-11 rounded-xl bg-blue-900/50 flex items-center justify-center border border-blue-800">
                    <span className="text-blue-300 font-bold">{ws.name.charAt(0)}</span>
                  </div>
                  <Badge variant="outline" className="border-slate-700 text-slate-400 text-xs">
                    Active
                  </Badge>
                </div>
                <CardTitle className="text-white text-lg mt-3 group-hover:text-blue-300 transition-colors">
                  {ws.name}
                </CardTitle>
                <CardDescription className="text-slate-400 line-clamp-2">
                  {ws.description ?? "No description added yet"}
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    <Calendar className="h-3 w-3" />
                    {new Date(ws.created_at).toLocaleDateString()}
                  </div>
                  <ArrowRight className="h-4 w-4 text-slate-600 group-hover:text-blue-400 transition-colors" />
                </div>
              </CardContent>
            </Card>
          ))}
          {/* New workspace card */}
          <Card
            className="bg-slate-900/50 border-slate-800 border-dashed hover:border-blue-700 cursor-pointer transition-all"
            onClick={() => setShowCreate(true)}
          >
            <CardContent className="flex flex-col items-center justify-center h-full min-h-44 gap-2">
              <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center">
                <Plus className="h-5 w-5 text-slate-400" />
              </div>
              <p className="text-slate-400 text-sm">New workspace</p>
            </CardContent>
          </Card>
        </div>
      )}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="bg-slate-900 border-slate-800 text-white">
          <DialogHeader>
            <DialogTitle>Create Workspace</DialogTitle>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              createMutation.mutate();
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label className="text-slate-300">Workspace Name</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Client Dashboard Q2"
                required
                className="bg-slate-800 border-slate-700 text-white"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-slate-300">Description (optional)</Label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What is this workspace for?"
                className="bg-slate-800 border-slate-700 text-white resize-none"
                rows={3}
              />
            </div>
            <div className="flex gap-3 justify-end">
              <Button type="button" variant="outline" onClick={() => setShowCreate(false)} className="border-slate-700">
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
