"use client";

import { useEffect, useRef } from "react";

import { AssistantMessage } from "@/components/chat/AssistantMessage";
import { UserMessage } from "@/components/chat/UserMessage";
import type { DisplayMessage } from "@/lib/use-chat-session";

type Props = {
  messages: DisplayMessage[];
  onCiteClick: (sourceId: string) => void;
};

export function Conversation({ messages, onCiteClick }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-6">
        <p className="text-center text-muted-foreground">
          Ask a question about your organization&apos;s regulatory documents.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-6 py-6">
      {messages.map((message) =>
        message.role === "USER" ? (
          <UserMessage key={message.id} content={message.content} />
        ) : (
          <AssistantMessage key={message.id} message={message} onCiteClick={onCiteClick} />
        )
      )}
      <div ref={bottomRef} />
    </div>
  );
}
