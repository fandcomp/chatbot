import { apiClient } from "@/lib/api-client";
import type { ConversationDetail, ConversationSummary } from "@/lib/chat-schemas";

export type FeedbackRating = "THUMBS_UP" | "THUMBS_DOWN";

export type FeedbackResult = {
  id: string;
  message_id: string;
  rating: FeedbackRating;
  comment: string | null;
};

export const chatApi = {
  listConversations: () => apiClient.get<ConversationSummary[]>("/conversations"),
  getConversation: (id: string) => apiClient.get<ConversationDetail>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    apiClient.patch<ConversationSummary>(`/conversations/${id}`, { title }),
  deleteConversation: (id: string) => apiClient.delete<void>(`/conversations/${id}`),
  submitFeedback: (messageId: string, rating: FeedbackRating) =>
    apiClient.post<FeedbackResult>(`/messages/${messageId}/feedback`, { rating }),
};
