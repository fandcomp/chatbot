"use client";

import { useEffect } from "react";

import { Composer } from "@/components/chat/Composer";
import { Conversation } from "@/components/chat/Conversation";
import { useChatSession, type DisplayMessage } from "@/lib/use-chat-session";
import type { Message } from "@/lib/chat-schemas";

type Props = {
  conversationId: string | undefined;
  initialMessages: Message[];
  onConversationCreated: (conversationId: string) => void;
  onCiteClick: (sourceId: string) => void;
  onMessagesChange: (messages: DisplayMessage[]) => void;
};

export function ChatSessionView({
  conversationId,
  initialMessages,
  onConversationCreated,
  onCiteClick,
  onMessagesChange,
}: Props) {
  const { messages, isStreaming, sendMessage, stopStreaming } = useChatSession(conversationId, {
    initialMessages,
    onConversationCreated,
  });

  useEffect(() => {
    onMessagesChange(messages);
  }, [messages, onMessagesChange]);

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <Conversation messages={messages} onCiteClick={onCiteClick} />
      <Composer
        isStreaming={isStreaming}
        onSubmit={(query) => void sendMessage(query)}
        onStop={stopStreaming}
      />
    </div>
  );
}
