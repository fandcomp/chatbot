"use client";

import { useCallback, useRef, useState } from "react";

import { streamChat } from "@/lib/chat-stream";
import type { Citation, Message, VerifiedClaim } from "@/lib/chat-schemas";

export type DisplayMessage = {
  id: string;
  role: "USER" | "ASSISTANT";
  content: string;
  isStreaming?: boolean;
  isError?: boolean;
  claims?: VerifiedClaim[];
  citations?: Record<string, Citation>;
  insufficientEvidence?: boolean;
};

const GENERIC_ERROR_MESSAGE = "Something went wrong while generating a response. Please try again.";

type UseChatSessionOptions = {
  initialMessages?: Message[];
  onConversationCreated?: (conversationId: string) => void;
};

export function useChatSession(
  conversationId: string | undefined,
  { initialMessages = [], onConversationCreated }: UseChatSessionOptions = {}
) {
  const [messages, setMessages] = useState<DisplayMessage[]>(() =>
    initialMessages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
    }))
  );
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (query: string) => {
      setError(null);
      const assistantId = crypto.randomUUID();
      setMessages((current) => [
        ...current,
        { id: crypto.randomUUID(), role: "USER", content: query },
        { id: assistantId, role: "ASSISTANT", content: "", isStreaming: true },
      ]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const { conversationId: newConversationId, events } = await streamChat(
          query,
          conversationId,
          controller.signal
        );

        for await (const event of events) {
          if (event.type === "token") {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, content: message.content + event.text }
                  : message
              )
            );
          } else if (event.type === "sources") {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      isStreaming: false,
                      claims: event.data.claims,
                      citations: event.data.citations,
                      insufficientEvidence: event.data.insufficient_evidence,
                    }
                  : message
              )
            );
          } else if (event.type === "error") {
            setError(event.message);
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? {
                      ...message,
                      // A mid-stream error can arrive after some tokens
                      // already rendered — append rather than replace, so
                      // partial output isn't silently discarded.
                      content: message.content
                        ? `${message.content}\n\n${GENERIC_ERROR_MESSAGE}`
                        : GENERIC_ERROR_MESSAGE,
                      isStreaming: false,
                      isError: true,
                    }
                  : message
              )
            );
          }
        }

        if (!conversationId && newConversationId) {
          onConversationCreated?.(newConversationId);
        }
      } catch (caught: unknown) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        const message = caught instanceof Error ? caught.message : "Something went wrong";
        setError(message);
        setMessages((current) =>
          current.map((existing) =>
            existing.id === assistantId
              ? { ...existing, content: GENERIC_ERROR_MESSAGE, isStreaming: false, isError: true }
              : existing
          )
        );
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [conversationId, onConversationCreated]
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, isStreaming, error, sendMessage, stopStreaming };
}
