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
  page_start: number;
  page_end: number;
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
