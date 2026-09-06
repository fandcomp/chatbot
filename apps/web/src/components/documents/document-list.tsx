"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import {
  ACTIVE_JOB_STATUSES,
  documentsApi,
  type DocumentItem,
  type DocumentLifecycleStatus,
  type ProcessingJobStatus,
} from "@/lib/documents-api";

const POLL_INTERVAL_MS = 3000;

// Chunking (M5) only ever runs once a version passes APPROVED, so Test
// Knowledge (spec §61) has something to query starting there — it works
// regardless of whether the document has reached ACTIVE yet.
const TEST_KNOWLEDGE_STATUSES = new Set<DocumentLifecycleStatus>([
  "APPROVED",
  "INDEXING",
  "ACTIVE",
  "SUPERSEDED",
  "ARCHIVED",
]);

type Props = {
  refreshToken: number;
};

export function DocumentList({ refreshToken }: Props) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [jobStatusOverrides, setJobStatusOverrides] = useState<
    Record<string, ProcessingJobStatus>
  >({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const versionTargetId = useRef<string | null>(null);
  const versionFileInput = useRef<HTMLInputElement>(null);
  const pollIntervals = useRef<Record<string, ReturnType<typeof setInterval>>>({});
  // Mirrors which documents' jobs have already reached a terminal status, so
  // the polling effect below can skip them without needing jobStatusOverrides
  // (reactive state) as a dependency — that would tear down and restart every
  // still-active interval on every poll tick.
  const resolvedDocumentIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    documentsApi
      .listDocuments()
      .then(setDocuments)
      .finally(() => setIsLoading(false));
  }, [refreshToken]);

  useEffect(() => {
    const intervals = pollIntervals.current;

    for (const document of documents) {
      if (intervals[document.id]) continue;
      if (!document.latest_processing_job_id) continue;
      if (resolvedDocumentIds.current.has(document.id)) continue;

      // We poll the ProcessingJob (not the document) because it's the thing
      // that resolves after upload; once it reaches a terminal status we
      // refetch the document list so latest_version_status (PARSED/
      // REVIEW_REQUIRED/PROCESSING_FAILED) reflects what M3's parser set,
      // instead of going stale at whatever it was when this poll started.
      const jobId = document.latest_processing_job_id;
      intervals[document.id] = setInterval(async () => {
        try {
          const job = await documentsApi.getProcessingJob(jobId);
          setJobStatusOverrides((current) => ({ ...current, [document.id]: job.status }));
          if (!ACTIVE_JOB_STATUSES.includes(job.status)) {
            resolvedDocumentIds.current.add(document.id);
            clearInterval(intervals[document.id]);
            delete intervals[document.id];
            documentsApi.listDocuments().then(setDocuments).catch(() => undefined);
          }
        } catch {
          resolvedDocumentIds.current.add(document.id);
          clearInterval(intervals[document.id]);
          delete intervals[document.id];
        }
      }, POLL_INTERVAL_MS);
    }

    return () => {
      for (const id of Object.keys(intervals)) {
        clearInterval(intervals[id]);
        delete intervals[id];
      }
    };
  }, [documents]);

  async function handleDelete(id: string) {
    await documentsApi.deleteDocument(id);
    setDocuments((current) => current.filter((document) => document.id !== id));
  }

  async function handleArchive(id: string) {
    setError(null);
    try {
      await documentsApi.archiveDocument(id);
      documentsApi.listDocuments().then(setDocuments).catch(() => undefined);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Archive failed");
    }
  }

  function handleUploadNewVersionClick(id: string) {
    versionTargetId.current = id;
    versionFileInput.current?.click();
  }

  async function handleVersionFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    const documentId = versionTargetId.current;
    event.target.value = "";
    if (!file || !documentId) return;

    setError(null);
    try {
      await documentsApi.uploadNewVersion(documentId, file);
      documentsApi.listDocuments().then(setDocuments).catch(() => undefined);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Upload failed");
    }
  }

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading documents…</p>;
  }

  if (documents.length === 0) {
    return <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {error && <p className="text-sm text-destructive">{error}</p>}
      <input
        ref={versionFileInput}
        type="file"
        accept=".pdf,.docx"
        className="hidden"
        onChange={(event) => void handleVersionFileSelected(event)}
      />
      <ul className="flex flex-col gap-2">
        {documents.map((document) => (
          <li
            key={document.id}
            className="flex items-center justify-between rounded-md border border-input px-4 py-3"
          >
            <div>
              <p className="text-sm font-medium">{document.title}</p>
              <p className="text-xs text-muted-foreground">
                {jobStatusOverrides[document.id] ?? document.latest_version_status}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {document.latest_version_status === "REVIEW_REQUIRED" && (
                <Button
                  variant="outline"
                  size="sm"
                  nativeButton={false}
                  render={<Link href={`/documents/${document.id}/structure`} />}
                >
                  Review structure
                </Button>
              )}
              {TEST_KNOWLEDGE_STATUSES.has(document.latest_version_status) && (
                <Button
                  variant="outline"
                  size="sm"
                  nativeButton={false}
                  render={<Link href={`/documents/${document.id}/test`} />}
                >
                  Test Knowledge
                </Button>
              )}
              {document.latest_version_status === "ACTIVE" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void handleArchive(document.id)}
                >
                  Archive
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleUploadNewVersionClick(document.id)}
              >
                New version
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void handleDelete(document.id)}>
                Delete
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
