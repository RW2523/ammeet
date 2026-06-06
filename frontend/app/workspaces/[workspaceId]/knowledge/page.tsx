"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { knowledgeApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { BookOpen, Send, ArrowLeft } from "lucide-react";
import Link from "next/link";

const SAMPLE_QUERIES = [
  "What should I ask in today's meeting?",
  "What did the client say last time?",
  "Which items are still blocked?",
  "What decisions were made?",
  "Generate follow-up questions for the next meeting.",
  "Who owns the API issue?",
];

export default function KnowledgePage() {
  const params = useParams();
  const workspaceId = params.workspaceId as string;
  const [query, setQuery] = useState("");
  const [history, setHistory] = useState<Array<{ query: string; answer: string; sources: unknown[] }>>([]);

  const mutation = useMutation({
    mutationFn: () => knowledgeApi.query(workspaceId, query),
    onSuccess: (data) => {
      setHistory((h) => [{ query, answer: data.answer, sources: data.sources }, ...h]);
      setQuery("");
    },
  });

  return (
    <div className="p-8">
      <div className="flex items-center gap-3 mb-8">
        <Link href={`/workspaces/${workspaceId}`}>
          <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <BookOpen className="h-8 w-8 text-blue-400" /> Knowledge Base
          </h1>
          <p className="text-slate-400 mt-1">Ask anything about your past meetings and project history</p>
        </div>
      </div>

      {/* Query bar */}
      <Card className="bg-slate-900 border-slate-800 mb-6">
        <CardContent className="p-4">
          <form
            onSubmit={(e) => { e.preventDefault(); if (query.trim()) mutation.mutate(); }}
            className="flex gap-3"
          >
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask about your meetings..."
              className="bg-slate-800 border-slate-700 text-white flex-1"
            />
            <Button type="submit" disabled={mutation.isPending || !query.trim()}>
              <Send className="h-4 w-4 mr-2" />
              {mutation.isPending ? "Searching..." : "Ask"}
            </Button>
          </form>

          {/* Sample queries */}
          <div className="flex flex-wrap gap-2 mt-3">
            {SAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => setQuery(q)}
                className="text-xs text-slate-400 bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-full transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {mutation.isPending && (
        <Card className="bg-slate-900 border-slate-800 mb-4">
          <CardContent className="p-5 space-y-3">
            <Skeleton className="h-4 w-3/4 bg-slate-800" />
            <Skeleton className="h-4 w-full bg-slate-800" />
            <Skeleton className="h-4 w-2/3 bg-slate-800" />
          </CardContent>
        </Card>
      )}

      {/* Response history */}
      {history.length === 0 && !mutation.isPending && (
        <Card className="bg-slate-900 border-slate-800 border-dashed">
          <CardContent className="p-10 text-center">
            <BookOpen className="h-10 w-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Ask a question about your meeting history, decisions, blockers, or action items.</p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-4">
        {history.map((item, i) => (
          <Card key={i} className="bg-slate-900 border-slate-800">
            <CardHeader className="pb-2">
              <p className="text-sm font-medium text-blue-300">"{item.query}"</p>
            </CardHeader>
            <CardContent className="pt-0">
              <p className="text-slate-300 leading-relaxed">{item.answer}</p>
              {(item.sources as unknown[]).length > 0 && (
                <div className="mt-3 pt-3 border-t border-slate-800">
                  <p className="text-xs text-slate-500 mb-2">Sources:</p>
                  <div className="flex gap-2 flex-wrap">
                    {(item.sources as Array<{ source_type: string; excerpt: string }>).map((s, j) => (
                      <div key={j} className="text-xs bg-slate-800 rounded px-2 py-1 text-slate-400">
                        {s.source_type}: "{s.excerpt}"
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
