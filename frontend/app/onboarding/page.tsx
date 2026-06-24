"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { workspaceApi, peopleApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowRight, Bot, Building2, CheckCircle, Users } from "lucide-react";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);

  // step 1 — workspace
  const [wsName, setWsName] = useState("");
  const [wsDescription, setWsDescription] = useState("");
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  // step 2 — first teammate (optional)
  const [personName, setPersonName] = useState("");
  const [personRole, setPersonRole] = useState("");

  const createWorkspace = async () => {
    setLoading(true);
    try {
      const ws = await workspaceApi.create({ name: wsName, description: wsDescription || undefined });
      setWorkspaceId(ws.id);
      setStep(2);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg || "Could not create workspace");
    } finally {
      setLoading(false);
    }
  };

  const addPerson = async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      if (personName.trim()) {
        await peopleApi.create(workspaceId, { name: personName, role: personRole || undefined });
      }
      setStep(3);
    } catch {
      toast.error("Could not add person — you can add people later.");
      setStep(3);
    } finally {
      setLoading(false);
    }
  };

  const steps = ["Welcome", "Workspace", "People", "Done"];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-xl space-y-6">
        {/* progress */}
        <div className="flex items-center justify-center gap-2">
          {steps.map((label, i) => (
            <div key={label} className="flex items-center gap-2">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                  ${i < step ? "bg-green-600 text-white" : i === step ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-500"}`}
              >
                {i < step ? <CheckCircle className="h-4 w-4" /> : i + 1}
              </div>
              {i < steps.length - 1 && <div className={`w-10 h-0.5 ${i < step ? "bg-green-600" : "bg-slate-800"}`} />}
            </div>
          ))}
        </div>

        {step === 0 && (
          <Card className="border-slate-700 bg-slate-800/50">
            <CardHeader className="text-center">
              <Bot className="h-12 w-12 text-blue-400 mx-auto mb-2" />
              <CardTitle className="text-white text-2xl">Welcome to AmMeeting</CardTitle>
              <CardDescription className="text-slate-400">
                In two minutes you&apos;ll have a workspace where AmMeeting preps questions,
                attends meetings as your transparent proxy, and writes the reports.
              </CardDescription>
            </CardHeader>
            <CardContent className="text-center">
              <Button onClick={() => setStep(1)} className="bg-blue-600 hover:bg-blue-500">
                Let&apos;s set up <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </CardContent>
          </Card>
        )}

        {step === 1 && (
          <Card className="border-slate-700 bg-slate-800/50">
            <CardHeader>
              <Building2 className="h-8 w-8 text-blue-400 mb-2" />
              <CardTitle className="text-white">Create your first workspace</CardTitle>
              <CardDescription className="text-slate-400">
                A workspace holds one project or team — its meetings, people, and knowledge base.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="text-slate-300">Workspace name</Label>
                <Input
                  value={wsName}
                  onChange={(e) => setWsName(e.target.value)}
                  placeholder="e.g. Client Dashboard Project"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">What is this project about? (optional)</Label>
                <Textarea
                  value={wsDescription}
                  onChange={(e) => setWsDescription(e.target.value)}
                  placeholder="A short description helps the AI ask better questions"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <Button onClick={createWorkspace} disabled={!wsName.trim() || loading} className="w-full">
                {loading ? "Creating..." : "Create workspace"}
              </Button>
            </CardContent>
          </Card>
        )}

        {step === 2 && (
          <Card className="border-slate-700 bg-slate-800/50">
            <CardHeader>
              <Users className="h-8 w-8 text-purple-400 mb-2" />
              <CardTitle className="text-white">Who do you meet with?</CardTitle>
              <CardDescription className="text-slate-400">
                Add one person you regularly meet — the AI uses people&apos;s roles and
                responsibilities to target questions. You can add more later.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label className="text-slate-300">Name</Label>
                <Input
                  value={personName}
                  onChange={(e) => setPersonName(e.target.value)}
                  placeholder="e.g. Sarah Chen"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-slate-300">Role</Label>
                <Input
                  value={personRole}
                  onChange={(e) => setPersonRole(e.target.value)}
                  placeholder="e.g. Design Lead"
                  className="bg-slate-700 border-slate-600 text-white"
                />
              </div>
              <div className="flex gap-3">
                <Button variant="outline" className="flex-1 border-slate-700 text-slate-300" onClick={() => setStep(3)}>
                  Skip
                </Button>
                <Button className="flex-1" onClick={addPerson} disabled={loading}>
                  {loading ? "Saving..." : "Continue"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {step === 3 && (
          <Card className="border-slate-700 bg-slate-800/50">
            <CardHeader className="text-center">
              <CheckCircle className="h-12 w-12 text-green-400 mx-auto mb-2" />
              <CardTitle className="text-white text-2xl">You&apos;re all set</CardTitle>
              <CardDescription className="text-slate-400">
                Next: create a meeting, upload a previous transcript or notes as context,
                and let AmMeeting generate your question list.
              </CardDescription>
            </CardHeader>
            <CardContent className="text-center space-y-3">
              <Button
                className="bg-blue-600 hover:bg-blue-500 w-full"
                onClick={() => router.push(workspaceId ? `/workspaces/${workspaceId}/meetings/new` : "/dashboard")}
              >
                Create your first meeting <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
              <Button variant="ghost" className="text-slate-400 w-full" onClick={() => router.push("/dashboard")}>
                Go to dashboard
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
