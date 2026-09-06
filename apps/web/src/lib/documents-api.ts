import { apiClient } from "@/lib/api-client";
import type { Citation } from "@/lib/chat-schemas";

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

// Specialized types (addendum §7) — only ever set by M4's interpreter, never
// by M3's generic parser.
export type DocumentNodeType =
  | "DOCUMENT"
  | "REGION"
  | "TITLE"
  | "SUBTITLE"
  | "CHAPTER"
  | "PART"
  | "SECTION"
  | "SUBSECTION"
  | "NUMBERED_SECTION"
  | "NUMBERED_ITEM"
  | "LETTER_ITEM"
  | "ROMAN_ITEM"
  | "NESTED_ITEM"
  | "ARTICLE"
  | "CLAUSE"
  | "DECISION_ITEM"
  | "PARAGRAPH"
  | "LIST"
  | "LIST_ITEM"
  | "TABLE"
  | "TABLE_ROW"
  | "TABLE_CELL"
  | "APPENDIX"
  | "FIGURE"
  | "DIAGRAM"
  | "FLOWCHART"
  | "ORGANIZATION_CHART"
  | "FOOTNOTE"
  | "SIGNATURE_BLOCK"
  | "UNKNOWN_BLOCK";

export type StructuralRegionType =
  | "COVER"
  | "TABLE_OF_CONTENTS"
  | "LEGAL_PREAMBLE"
  | "LEGAL_BODY"
  | "LEGAL_DECISION"
  | "TECHNICAL_GUIDELINE"
  | "PROCEDURAL_GUIDELINE"
  | "NUMBERED_MANUAL"
  | "SOP"
  | "APPENDIX"
  | "TABLE_REGION"
  | "DIAGRAM_REGION"
  | "ORGANIZATION_CHART"
  | "FLOWCHART"
  | "EMBEDDED_TEMPLATE"
  | "ACADEMIC_TEMPLATE"
  | "FREEFORM_SECTION"
  | "UNKNOWN";

export type StructurePathEntry = {
  node_type: string;
  label: string | null;
  title: string | null;
};

export type StructureNode = {
  id: string;
  region_id: string;
  parent_id: string | null;
  node_type: DocumentNodeType;
  semantic_role: string | null;
  label: string | null;
  title: string | null;
  text: string | null;
  number_raw: string | null;
  number_normalized: string | null;
  depth: number;
  sequence_number: number;
  page_start: number;
  page_end: number;
  confidence: number;
  structural_path_json: StructurePathEntry[];
  structural_path_text: string | null;
  structural_depth: number;
  chapter_number: string | null;
  article_number: string | null;
  clause_number: string | null;
  letter_number: string | null;
  appendix_number: string | null;
};

export type StructureRegion = {
  id: string;
  region_type: StructuralRegionType;
  page_start: number;
  page_end: number;
  sequence_number: number;
  confidence: number;
};

export type StructureProfile = {
  contains_articles: boolean;
  contains_numbered_sections: boolean;
  contains_chapters: boolean;
  contains_decision_preamble: boolean;
  contains_appendices: boolean;
  contains_tables: boolean;
  contains_diagrams: boolean;
  contains_embedded_document: boolean;
};

export type DocumentStructure = {
  document_version_id: string;
  version_status: DocumentLifecycleStatus;
  aggregate_confidence: number;
  regions: StructureRegion[];
  nodes: StructureNode[];
  profile: StructureProfile | null;
};

export type NodeCorrection = {
  node_type?: DocumentNodeType;
  parent_id?: string;
  label?: string;
  title?: string;
  region_type?: StructuralRegionType;
};

export type ApprovalResult = {
  document_id: string;
  document_version_id: string;
  status: DocumentLifecycleStatus;
};

export type ArchiveResult = {
  document_id: string;
  document_version_id: string;
  status: DocumentLifecycleStatus;
};

export type RetrievedSourcePreview = {
  chunk_id: string;
  structural_path_text: string | null;
  original_text: string;
  score: number | null;
};

export type TestKnowledgeResponse = {
  question: string;
  detected_intent: string;
  retrieval_mode: "EXACT_STRUCTURAL" | "HYBRID";
  retrieved_sources: RetrievedSourcePreview[];
  answer: string;
  insufficient_evidence: boolean;
  reason_if_insufficient: string | null;
  citations: Record<string, Citation>;
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
  getStructure: (documentId: string) =>
    apiClient.get<DocumentStructure>(`/documents/${documentId}/structure`),
  updateNode: (documentId: string, nodeId: string, correction: NodeCorrection) =>
    apiClient.patch<StructureNode>(
      `/documents/${documentId}/nodes/${nodeId}`,
      correction,
    ),
  approveDocument: (documentId: string) =>
    apiClient.post<ApprovalResult>(`/documents/${documentId}/approve`),
  testKnowledge: (documentId: string, query: string) =>
    apiClient.post<TestKnowledgeResponse>("/knowledge/test", { document_id: documentId, query }),
  uploadNewVersion: (documentId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient.upload<UploadResponse>(`/documents/${documentId}/versions`, formData);
  },
  archiveDocument: (documentId: string) =>
    apiClient.post<ArchiveResult>(`/documents/${documentId}/archive`),
};

export const ACTIVE_JOB_STATUSES: ProcessingJobStatus[] = ["QUEUED", "PROCESSING"];
