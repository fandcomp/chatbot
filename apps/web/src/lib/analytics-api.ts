import { apiClient } from "@/lib/api-client";

export type AnalyticsOverview = {
  total_questions: number;
  answered: number;
  insufficient_evidence: number;
  avg_latency_ms: number | null;
  p95_latency_ms: number | null;
  avg_cost_usd: number | null;
  citation_coverage: number;
  retrieval_success: number;
  cache_hit_rate: number;
  thumbs_up: number;
  thumbs_down: number;
};

export type KnowledgeGap = {
  query: string;
  frequency: number;
  last_asked_at: string;
};

export type TopQuestion = {
  query: string;
  frequency: number;
  last_asked_at: string;
};

export type DocumentMention = {
  document_id: string;
  document_title: string;
  citation_count: number;
};

export type DocumentStatusCount = {
  status: string;
  count: number;
};

// spec §82's illustrative Admin Overview.
export type KnowledgeBaseOverview = {
  total_documents: number;
  total_indexed_chunks: number;
  status_breakdown: DocumentStatusCount[];
};

export const analyticsApi = {
  getOverview: () => apiClient.get<AnalyticsOverview>("/analytics/overview"),
  getKnowledgeBaseOverview: () =>
    apiClient.get<KnowledgeBaseOverview>("/analytics/knowledge-base"),
  listKnowledgeGaps: () => apiClient.get<KnowledgeGap[]>("/analytics/knowledge-gaps"),
  listTopQuestions: () => apiClient.get<TopQuestion[]>("/analytics/questions"),
  listTopSources: () => apiClient.get<DocumentMention[]>("/analytics/sources"),
};
