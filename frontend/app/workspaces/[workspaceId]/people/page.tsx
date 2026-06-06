"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { peopleApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Plus, Pencil, Trash2, User, ExternalLink } from "lucide-react";
import type { Person } from "@/lib/types";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

const EMPTY: Partial<Person> = { name: "", role: "", responsibility: "", current_work: "", decision_authority: "", follow_up: "", email: "", is_external: false };

export default function PeoplePage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Person | null>(null);
  const [form, setForm] = useState<Partial<Person>>(EMPTY);

  const { data: people, isLoading } = useQuery({
    queryKey: ["people", workspaceId],
    queryFn: () => peopleApi.list(workspaceId),
  });

  const createMutation = useMutation({
    mutationFn: () => peopleApi.create(workspaceId, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["people", workspaceId] }); toast.success("Person added"); setShowForm(false); setForm(EMPTY); },
    onError: () => toast.error("Failed to add person"),
  });

  const updateMutation = useMutation({
    mutationFn: () => peopleApi.update(workspaceId, editing!.id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["people", workspaceId] }); toast.success("Updated"); setEditing(null); setForm(EMPTY); },
    onError: () => toast.error("Failed to update"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => peopleApi.delete(workspaceId, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["people", workspaceId] }); toast.success("Removed"); },
    onError: () => toast.error("Failed to remove"),
  });

  const openEdit = (p: Person) => { setEditing(p); setForm({ name: p.name, role: p.role ?? "", responsibility: p.responsibility ?? "", current_work: p.current_work ?? "", decision_authority: p.decision_authority ?? "", follow_up: p.follow_up ?? "", email: p.email ?? "", is_external: p.is_external }); };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <Link href={`/workspaces/${workspaceId}`}>
            <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-3xl font-bold text-white">People & Roles</h1>
            <p className="text-slate-400 mt-1">Track attendees, responsibilities, and follow-ups</p>
          </div>
        </div>
        <Button onClick={() => { setShowForm(true); setForm(EMPTY); }}>
          <Plus className="h-4 w-4 mr-2" /> Add Person
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3].map((i) => <Card key={i} className="bg-slate-900 border-slate-800 animate-pulse h-40" />)}
        </div>
      ) : people?.length === 0 ? (
        <Card className="bg-slate-900 border-slate-800 border-dashed">
          <CardContent className="p-10 text-center">
            <User className="h-10 w-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400 mb-5">Add people to track their roles, current work, and follow-up questions.</p>
            <Button onClick={() => setShowForm(true)}>Add First Person</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {people?.map((p) => (
            <Card key={p.id} className="bg-slate-900 border-slate-800 group">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0">
                      <span className="text-white font-bold">{p.name.charAt(0)}</span>
                    </div>
                    <div>
                      <CardTitle className="text-white text-base">{p.name}</CardTitle>
                      {p.role && <p className="text-sm text-slate-400">{p.role}</p>}
                    </div>
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-slate-500" onClick={() => openEdit(p)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500" onClick={() => deleteMutation.mutate(p.id)}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
                <div className="flex gap-1.5 flex-wrap mt-1">
                  {p.is_external && <Badge variant="outline" className="border-amber-700 text-amber-400 text-xs"><ExternalLink className="h-3 w-3 mr-1" />External</Badge>}
                </div>
              </CardHeader>
              <CardContent className="pt-0 space-y-1.5">
                {p.current_work && (
                  <div>
                    <p className="text-xs text-slate-500">Current Work</p>
                    <p className="text-sm text-slate-300">{p.current_work}</p>
                  </div>
                )}
                {p.follow_up && (
                  <div className="bg-blue-900/20 rounded-lg p-2">
                    <p className="text-xs text-blue-400">Follow-up needed</p>
                    <p className="text-sm text-blue-200">{p.follow_up}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={showForm || !!editing} onOpenChange={(o) => { if (!o) { setShowForm(false); setEditing(null); } }}>
        <DialogContent className="bg-slate-900 border-slate-800 text-white max-w-lg">
          <DialogHeader>
            <DialogTitle>{editing ? "Edit Person" : "Add Person"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={(e) => { e.preventDefault(); editing ? updateMutation.mutate() : createMutation.mutate(); }} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-slate-300 text-xs">Name *</Label>
                <Input value={form.name ?? ""} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} required className="bg-slate-800 border-slate-700 text-white text-sm" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-slate-300 text-xs">Role</Label>
                <Input value={form.role ?? ""} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} className="bg-slate-800 border-slate-700 text-white text-sm" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-slate-300 text-xs">Current Work</Label>
              <Input value={form.current_work ?? ""} onChange={(e) => setForm((f) => ({ ...f, current_work: e.target.value }))} className="bg-slate-800 border-slate-700 text-white text-sm" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-slate-300 text-xs">Follow-up Needed</Label>
              <Textarea value={form.follow_up ?? ""} onChange={(e) => setForm((f) => ({ ...f, follow_up: e.target.value }))} rows={2} className="bg-slate-800 border-slate-700 text-white text-sm resize-none" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-slate-300 text-xs">Decision Authority</Label>
              <Input value={form.decision_authority ?? ""} onChange={(e) => setForm((f) => ({ ...f, decision_authority: e.target.value }))} className="bg-slate-800 border-slate-700 text-white text-sm" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-slate-300 text-xs">Email</Label>
                <Input type="email" value={form.email ?? ""} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} className="bg-slate-800 border-slate-700 text-white text-sm" />
              </div>
              <div className="flex items-end gap-2 pb-1">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={form.is_external ?? false} onChange={(e) => setForm((f) => ({ ...f, is_external: e.target.checked }))} className="accent-blue-500" />
                  <span className="text-sm text-slate-300">External</span>
                </label>
              </div>
            </div>
            <div className="flex gap-3 justify-end pt-2">
              <Button type="button" variant="outline" className="border-slate-700" onClick={() => { setShowForm(false); setEditing(null); }}>Cancel</Button>
              <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
                {editing ? "Update" : "Add Person"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
