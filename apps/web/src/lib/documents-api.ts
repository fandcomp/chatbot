import { apiClient } from "@/lib/api-client";

export type KnowledgeSpace = {
  id: string;
  name: string;
  created_at: string;
};

export type DocumentLifecycleStatus =
  | "UPLOADED"
  | "PROCESSING"
  | "PARSED"
  | "REVIEW_REQUIRED"
  | "APPROVED"
  | "INDEXING"
  | "ACTIVE"
  | "PROCESSING_FAILED"
  | "SUPERSEDED"
  | "ARCHIVED";

export type ProcessingJobStatus = "QUEUED" | "PROCESSING" | "SUCCEEDED" | "FAILED";

export type DocumentItem = {
  id: string;
  title: string;
  knowledge_space_id: string;
  latest_version_id: string;
  latest_version_status: DocumentLifecycleStatus;
  latest_processing_job_id: string | null;
  created_at: string;
};

export type UploadResponse = {
  document_id: string;
  document_version_id: string;
  processing_job_id: string;
  status: DocumentLifecycleStatus;
};

export type ProcessingJob = {
  id: string;
  status: ProcessingJobStatus;
  attempts: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export const documentsApi = {
  listKnowledgeSpaces: () => apiClient.get<KnowledgeSpace[]>("/knowledge-spaces"),
  listDocuments: () => apiClient.get<DocumentItem[]>("/documents"),
  deleteDocument: (id: string) => apiClient.delete<void>(`/documents/${id}`),
  getProcessingJob: (id: string) => apiClient.get<ProcessingJob>(`/processing-jobs/${id}`),
  upload: (knowledgeSpaceId: string, file: File) => {
    const formData = new FormData();
    formData.append("knowledge_space_id", knowledgeSpaceId);
    formData.append("file", file);
    return apiClient.upload<UploadResponse>("/documents/upload", formData);
  },
};

export const ACTIVE_JOB_STATUSES: ProcessingJobStatus[] = ["QUEUED", "PROCESSING"];
