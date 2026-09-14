export type MessageRole = "USER" | "ASSISTANT";

export type ClaimStatus = "SUPPORTED" | "UNSUPPORTED" | "UNCERTAIN";

export type VerifiedClaim = {
  text: string;
  source_ids: string[];
  status: ClaimStatus;
  invalid_reason: string | null;
};

export type DocumentRelationType =
  | "AMENDS"
  | "REPEALS"
  | "REPLACES"
  | "IMPLEMENTS"
  | "REFERS_TO"
  | "SUPERSEDED_BY";

// ADR-021 — spec §53's access level, enforced server-side at retrieval
// time. Client-side use of this type is UX-only (showing/hiding the admin
// control); the backend's role-based filter is the real enforcement.
export type DocumentVisibility = "PUBLIC" | "INTERNAL" | "RESTRICTED";

// spec §21 — a relation where the cited document is the "to" side (e.g.
// another regulation AMENDS/REPEALS/REPLACES it), surfaced so a user citing
// this document learns it may no longer stand alone even though its own
// version is still ACTIVE.
export type RelatingDocument = {
  relation_type: DocumentRelationType;
  related_document_id: string;
  related_document_title: string;
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
  superseding_relations: RelatingDocument[];
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
  // The persisted ASSISTANT Message row's id — every branch of
  // stream_answer (including insufficient-evidence) appends one, so
  // feedback (thumbs up/down) always has a real target to submit against.
  message_id: string;
};
