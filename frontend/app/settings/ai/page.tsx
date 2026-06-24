"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { llmApi, type LLMConfigInfo, type LLMProviderInfo } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Bot, CheckCircle, Cpu, Eye, EyeOff, Settings2, XCircle, Zap } from "lucide-react";

export default function AIModelSettingsPage() {
  const { data: providers } = useQuery({ queryKey: ["llm-providers"], queryFn: () => llmApi.providers() });
  const { data: config } = useQuery({ queryKey: ["llm-config"], queryFn: () => llmApi.getConfig() });

  return (
    <div className="p-8 max-w-3xl">
      <div className="flex items-center gap-3 mb-8">
        <Link href="/dashboard">
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Cpu className="h-8 w-8 text-blue-400" /> AI Model
          </h1>
          <p className="text-slate-400 mt-1">Choose which AI provider and model power AmMeeting&apos;s features</p>
        </div>
      </div>

      {/* Current status */}
      <Card className="bg-slate-900 border-slate-800 mb-6">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-white text-base flex items-center gap-2">
              <Zap className="h-4 w-4 text-amber-400" /> Active configuration
            </CardTitle>
            {config?.has_key ? (
              <Badge className="bg-green-900 text-green-300 text-xs flex items-center gap-1">
                <CheckCircle className="h-3 w-3" /> Key set ({config.key_preview})
              </Badge>
            ) : (
              <Badge variant="outline" className="border-amber-800 text-amber-300 text-xs flex items-center gap-1">
                <XCircle className="h-3 w-3" /> No API key — running in mock/fallback mode
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="text-sm text-slate-400">
          {config ? (
            <span>
              Provider <span className="text-slate-200">{config.provider}</span> · model{" "}
              <span className="text-slate-200">{config.model}</span> · source{" "}
              <span className="text-slate-500">{config.source}</span>
            </span>
          ) : (
            "Loading…"
          )}
        </CardContent>
      </Card>

      {/* The form initializes its state from the loaded config (no effect needed) */}
      {config ? (
        <AIModelForm config={config} providers={providers ?? []} />
      ) : (
        <p className="text-slate-500 text-sm">Loading settings…</p>
      )}
    </div>
  );
}

function AIModelForm({ config, providers }: { config: LLMConfigInfo; providers: LLMProviderInfo[] }) {
  const qc = useQueryClient();
  const [provider, setProvider] = useState<string>(config.provider);
  const [model, setModel] = useState<string>(config.model || "");
  const [apiKey, setApiKey] = useState<string>("");
  const [showKey, setShowKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState<string>(config.base_url || "");
  const [embeddingModel, setEmbeddingModel] = useState<string>(config.embedding_model || "");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);

  const current = providers.find((p) => p.id === provider);

  const onPickProvider = (id: string) => {
    setProvider(id);
    const p = providers.find((x) => x.id === id);
    setModel(p?.default_model || "");
    setBaseUrl("");
    setEmbeddingModel("");
    setTestResult(null);
  };

  const saveMutation = useMutation({
    mutationFn: () =>
      llmApi.setConfig({
        provider,
        model: model || undefined,
        api_key: apiKey || undefined,
        embedding_model: embeddingModel || undefined,
        base_url: baseUrl || undefined,
      }),
    onSuccess: () => {
      setApiKey("");
      qc.invalidateQueries({ queryKey: ["llm-config"] });
      toast.success("AI model settings saved");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg || "Could not save settings");
    },
  });

  const testMutation = useMutation({
    mutationFn: () => llmApi.test(),
    onSuccess: (r) => {
      if (r.ok) {
        setTestResult({ ok: true, text: `Connected — model replied: "${r.sample}"` });
        toast.success("Connection successful");
      } else {
        setTestResult({ ok: false, text: r.error || "Test failed" });
        toast.error("Connection failed");
      }
    },
    onError: () => {
      setTestResult({ ok: false, text: "Request failed" });
      toast.error("Test request failed");
    },
  });

  return (
    <>
      {/* Provider picker */}
      <h2 className="text-sm font-medium text-slate-300 mb-3">Provider</h2>
      <div className="grid grid-cols-2 gap-3 mb-6">
        {providers.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onPickProvider(p.id)}
            className={`text-left rounded-xl border-2 p-4 transition-all ${
              provider === p.id ? "border-blue-600 bg-blue-900/20" : "border-slate-800 bg-slate-900/50 hover:border-slate-600"
            }`}
          >
            <div className="flex items-center gap-2">
              <Bot className={`h-4 w-4 ${provider === p.id ? "text-blue-400" : "text-slate-400"}`} />
              <span className={`font-medium ${provider === p.id ? "text-white" : "text-slate-300"}`}>{p.label}</span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {p.supports_embeddings ? "Chat + embeddings" : "Chat (keyword search fallback)"}
            </p>
          </button>
        ))}
      </div>

      {/* API key */}
      <div className="space-y-2 mb-5">
        <Label className="text-slate-300">API Key</Label>
        <div className="relative">
          <Input
            type={showKey ? "text" : "password"}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={config.has_key ? "•••••••• (leave blank to keep current key)" : current?.key_hint || "Paste your API key"}
            className="bg-slate-900 border-slate-700 text-white pr-10"
          />
          <button
            type="button"
            onClick={() => setShowKey((s) => !s)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
          >
            {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <p className="text-xs text-slate-500">
          Stored encrypted on the server. {current && <>Get a key from the {current.label} dashboard.</>}
        </p>
      </div>

      {/* Model */}
      <div className="space-y-2 mb-5">
        <Label className="text-slate-300">Model</Label>
        <div className="flex flex-wrap gap-2 mb-2">
          {current?.models.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setModel(m)}
              className={`text-xs px-2.5 py-1 rounded-full border ${
                model === m ? "border-blue-600 bg-blue-900/30 text-blue-200" : "border-slate-700 text-slate-400 hover:text-slate-200"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
        <Input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={current?.default_model}
          className="bg-slate-900 border-slate-700 text-white font-mono text-sm"
        />
        <p className="text-xs text-slate-500">Pick a suggestion or type any model id the provider supports.</p>
      </div>

      {/* Advanced */}
      <button
        type="button"
        onClick={() => setShowAdvanced((s) => !s)}
        className="text-sm text-slate-400 hover:text-white flex items-center gap-1.5 mb-3"
      >
        <Settings2 className="h-4 w-4" /> Advanced options {showAdvanced ? "▲" : "▼"}
      </button>
      {showAdvanced && (
        <div className="space-y-4 mb-6 border-l-2 border-slate-800 pl-4">
          <div className="space-y-2">
            <Label className="text-slate-300">Embedding model</Label>
            <Input
              value={embeddingModel}
              onChange={(e) => setEmbeddingModel(e.target.value)}
              placeholder={current?.supports_embeddings ? "e.g. text-embedding-3-small" : "(not supported — uses keyword search)"}
              className="bg-slate-900 border-slate-700 text-white font-mono text-sm"
            />
            <p className="text-xs text-slate-500">Used for the knowledge-base semantic search.</p>
          </div>
          <div className="space-y-2">
            <Label className="text-slate-300">Base URL override</Label>
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={current?.default_base_url}
              className="bg-slate-900 border-slate-700 text-white font-mono text-sm"
            />
            <p className="text-xs text-slate-500">Leave blank to use the provider default. Set for self-hosted/proxy endpoints.</p>
          </div>
        </div>
      )}

      {/* Test result */}
      {testResult && (
        <div
          className={`rounded-lg p-3 mb-4 text-sm flex items-start gap-2 ${
            testResult.ok ? "bg-green-900/20 border border-green-800 text-green-200" : "bg-red-900/20 border border-red-800 text-red-200"
          }`}
        >
          {testResult.ok ? <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" /> : <XCircle className="h-4 w-4 mt-0.5 shrink-0" />}
          <span className="break-all">{testResult.text}</span>
        </div>
      )}

      <div className="flex gap-3">
        <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="bg-blue-600 hover:bg-blue-500">
          {saveMutation.isPending ? "Saving…" : "Save settings"}
        </Button>
        <Button
          variant="outline"
          onClick={() => testMutation.mutate()}
          disabled={testMutation.isPending}
          className="border-slate-700 text-slate-300"
        >
          {testMutation.isPending ? "Testing…" : "Test connection"}
        </Button>
      </div>

      <Card className="bg-slate-900/50 border-slate-800 mt-8">
        <CardHeader className="pb-2">
          <CardDescription className="text-slate-400 text-sm">
            This setting applies to the whole instance — it powers question generation, the live proxy answers,
            clarifying questions, escalation analysis, and report writing. Save your key, then <strong>Test connection</strong> to confirm.
          </CardDescription>
        </CardHeader>
        <CardContent />
      </Card>
    </>
  );
}
