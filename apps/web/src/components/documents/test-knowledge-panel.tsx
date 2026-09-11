"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api-client";
import { documentsApi, type TestKnowledgeResponse } from "@/lib/documents-api";

type Props = {
  documentId: string;
};

/**
 * §61's admin preview: Question / Detected Intent / Retrieved Sources
 * (with Scores) / Answer / Citation — queries this one document directly,
 * regardless of its current lifecycle status (POST /knowledge/test).
 */
export function TestKnowledgePanel({ documentId }: Props) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<TestKnowledgeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) return;

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await documentsApi.testKnowledge(documentId, query.trim());
      setResult(response);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong");
      setResult(null);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Test Knowledge</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <form className="flex items-end gap-2" onSubmit={handleSubmit}>
          <div className="flex flex-1 flex-col gap-1.5">
            <Label htmlFor="test-knowledge-query">Question</Label>
            <Input
              id="test-knowledge-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. Apa isi Pasal 5?"
            />
          </div>
          <Button type="submit" disabled={isSubmitting || query.trim().length === 0}>
            {isSubmitting ? "Testing…" : "Test"}
          </Button>
        </form>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {result && (
          <div className="flex flex-col gap-4 rounded-lg border border-border p-4 text-sm">
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase">
                Detected Intent
              </p>
              <p>{result.detected_intent}</p>
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase">
                Retrieved Sources ({result.retrieval_mode === "EXACT_STRUCTURAL" ? "exact" : "hybrid"})
              </p>
              {result.retrieved_sources.length === 0 ? (
                <p className="text-muted-foreground">No sources retrieved.</p>
              ) : (
                <ul className="mt-1 flex flex-col gap-2">
                  {result.retrieved_sources.map((source) => (
                    <li key={source.chunk_id} className="rounded-md bg-muted/40 p-2">
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{source.structural_path_text ?? "(no structural path)"}</span>
                        {source.score !== null && <span>score: {source.score.toFixed(4)}</span>}
                      </div>
                      <p className="mt-1 whitespace-pre-wrap">{source.original_text}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase">Answer</p>
              <p className="whitespace-pre-wrap">{result.answer}</p>
            </div>

            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase">Citation</p>
              {Object.keys(result.citations).length === 0 ? (
                <p className="text-muted-foreground">No citations.</p>
              ) : (
                <ul className="mt-1 flex flex-col gap-1">
                  {Object.entries(result.citations).map(([sourceId, citation]) => (
                    <li key={sourceId} className="text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{sourceId}</span> —{" "}
                      {citation.document_title}
                      {citation.structural_path_text ? `, ${citation.structural_path_text}` : ""}
                      {citation.page_start !== null ? `, p.${citation.page_start}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
