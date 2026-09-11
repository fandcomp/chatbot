export type MessageRole = "USER" | "ASSISTANT";

export type ClaimStatus = "SUPPORTED" | "UNSUPPORTED" | "UNCERTAIN";

export type VerifiedClaim = {
  text: string;
  source_ids: string[];
  status: ClaimStatus;
  invalid_reason: string | null;
};

export type Citation = {
  source_id: string;
  document_id: string;
  document_title: string;
  structural_path_text: string | null;
  // Null for DOCX-derived evidence — no stable page number exists there at
  // all; structural_path_text is the real citation location.
  page_start: number | null;
  page_end: number | null;
  original_text_excerpt: string;
};

export type ConversationSummary = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  role: MessageRole;
  content: string;
  created_at: string;
};

export type ConversationDetail = ConversationSummary & {
  messages: Message[];
};

export type StreamSourcesEvent = {
  insufficient_evidence: boolean;
  claims: VerifiedClaim[];
  citations: Record<string, Citation>;
};
