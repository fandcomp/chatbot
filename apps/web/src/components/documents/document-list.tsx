"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  ACTIVE_JOB_STATUSES,
  documentsApi,
  type DocumentItem,
  type ProcessingJobStatus,
} from "@/lib/documents-api";

const POLL_INTERVAL_MS = 3000;

type Props = {
  refreshToken: number;
};

export function DocumentList({ refreshToken }: Props) {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [jobStatusOverrides, setJobStatusOverrides] = useState<
    Record<string, ProcessingJobStatus>
  >({});
  const [isLoading, setIsLoading] = useState(true);
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

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading documents…</p>;
  }

  if (documents.length === 0) {
    return <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>;
  }

  return (
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
                render={<Link href={`/documents/${document.id}/structure`} />}
              >
                Review structure
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => void handleDelete(document.id)}>
              Delete
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
