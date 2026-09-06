"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { TestKnowledgePanel } from "@/components/documents/test-knowledge-panel";
import { Button } from "@/components/ui/button";

export default function TestKnowledgePage() {
  const params = useParams<{ documentId: string }>();

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Test Knowledge</h1>
          <p className="text-sm text-muted-foreground">
            Preview answer quality for this document before it goes live.
          </p>
        </div>
        <Button variant="ghost" nativeButton={false} render={<Link href="/documents" />}>
          Back to documents
        </Button>
      </div>

      <TestKnowledgePanel documentId={params.documentId} />
    </div>
  );
}
