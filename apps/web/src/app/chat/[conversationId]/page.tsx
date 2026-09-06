"use client";

import { useParams } from "next/navigation";

import { ChatPage } from "@/components/chat/ChatPage";

export default function ExistingChatPage() {
  const params = useParams<{ conversationId: string }>();
  return <ChatPage conversationId={params.conversationId} />;
}
