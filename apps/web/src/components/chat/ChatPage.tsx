"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ChatSessionView } from "@/components/chat/ChatSessionView";
import { Sidebar } from "@/components/chat/Sidebar";
import { SourceDrawer } from "@/components/chat/SourceDrawer";
import { chatApi } from "@/lib/chat-api";
import type { Citation, ConversationSummary, Message } from "@/lib/chat-schemas";
import type { DisplayMessage } from "@/lib/use-chat-session";

type Props = {
  conversationId?: string;
};

export function ChatPage({ conversationId }: Props) {
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  // Tracks which conversationId the currently-loaded messages belong to, so
  // isLoading/initialMessages below can be *derived* during render rather
  // than tracked as separate state kept in sync via effects.
  const [loaded, setLoaded] = useState<{ conversationId: string | undefined; messages: Message[] }>(
    { conversationId: undefined, messages: [] }
  );
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);

  useEffect(() => {
    chatApi
      .listConversations()
      .then(setConversations)
      .catch(() => undefined);
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) return;
    let cancelled = false;
    chatApi.getConversation(conversationId).then((detail) => {
      if (!cancelled) setLoaded({ conversationId, messages: detail.messages });
    });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const isLoading = Boolean(conversationId) && loaded.conversationId !== conversationId;
  const initialMessages = loaded.conversationId === conversationId ? loaded.messages : [];

  const handleConversationCreated = useCallback(
    (newConversationId: string) => {
      router.push(`/chat/${newConversationId}`);
    },
    [router]
  );

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      await chatApi.deleteConversation(id);
      setConversations((current) => current.filter((conversation) => conversation.id !== id));
      if (id === conversationId) router.push("/chat");
    },
    [conversationId, router]
  );

  const [lastMessages, setLastMessages] = useState<DisplayMessage[]>([]);
  const handleCiteClick = useCallback(
    (sourceId: string) => {
      const lastAssistant = [...lastMessages].reverse().find((m) => m.role === "ASSISTANT");
      setActiveCitation(lastAssistant?.citations?.[sourceId] ?? null);
    },
    [lastMessages]
  );

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeConversationId={conversationId}
        onDeleteConversation={(id) => void handleDeleteConversation(id)}
      />
      {isLoading ? (
        <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
          Loading…
        </div>
      ) : (
        <ChatSessionView
          key={conversationId ?? "new"}
          conversationId={conversationId}
          initialMessages={initialMessages}
          onConversationCreated={handleConversationCreated}
          onCiteClick={handleCiteClick}
          onMessagesChange={setLastMessages}
        />
      )}
      <SourceDrawer citation={activeCitation} onClose={() => setActiveCitation(null)} />
    </div>
  );
}
