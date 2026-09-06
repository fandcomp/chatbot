"use client";

import { BarChart3Icon, FileTextIcon, LogOutIcon, PanelLeftIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ChatHistory } from "@/components/chat/ChatHistory";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";
import type { ConversationSummary } from "@/lib/chat-schemas";

type Props = {
  conversations: ConversationSummary[];
  activeConversationId: string | undefined;
  onDeleteConversation: (id: string) => void;
};

export function Sidebar({ conversations, activeConversationId, onDeleteConversation }: Props) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const { state, logout } = useAuth();
  // Analytics is an OWNER/ADMIN/EDITOR capability (matches the backend's own
  // require_role check, app/analytics/router.py) — hiding the link for
  // VIEWER is a UX nicety only, never the enforcement (the API still 403s).
  const canSeeAnalytics = state.status === "authenticated" && state.role !== "VIEWER";

  if (isCollapsed) {
    return (
      <div className="flex w-14 flex-col items-center gap-2 border-r border-border bg-sidebar py-3">
        <Button variant="ghost" size="icon" onClick={() => setIsCollapsed(false)}>
          <PanelLeftIcon />
          <span className="sr-only">Expand sidebar</span>
        </Button>
        <Button variant="ghost" size="icon" nativeButton={false} render={<Link href="/chat" />}>
          <PlusIcon />
          <span className="sr-only">New chat</span>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex w-64 shrink-0 flex-col border-r border-border bg-sidebar">
      <div className="flex items-center justify-between px-3 py-3">
        <span className="text-sm font-semibold tracking-tight">Regulatory Assistant</span>
        <Button variant="ghost" size="icon-sm" onClick={() => setIsCollapsed(true)}>
          <PanelLeftIcon className="size-4" />
          <span className="sr-only">Collapse sidebar</span>
        </Button>
      </div>

      <div className="px-2">
        <Button
          variant="secondary"
          className={cn("w-full justify-start gap-2")}
          nativeButton={false}
          render={<Link href="/chat" />}
        >
          <PlusIcon className="size-4" />
          New chat
        </Button>
      </div>

      <div className="flex flex-col gap-1 px-2 pt-2">
        <Button
          variant="ghost"
          className="w-full justify-start gap-2"
          nativeButton={false}
          render={<Link href="/documents" />}
        >
          <FileTextIcon className="size-4" />
          Documents
        </Button>
        {canSeeAnalytics && (
          <Button
            variant="ghost"
            className="w-full justify-start gap-2"
            nativeButton={false}
            render={<Link href="/analytics" />}
          >
            <BarChart3Icon className="size-4" />
            Analytics
          </Button>
        )}
      </div>

      <div className="mt-3 flex-1 overflow-y-auto px-2">
        <ChatHistory
          conversations={conversations}
          activeConversationId={activeConversationId}
          onDelete={onDeleteConversation}
        />
      </div>

      <div className="border-t border-border p-2">
        <Button variant="ghost" className="w-full justify-start gap-2" onClick={() => void logout()}>
          <LogOutIcon className="size-4" />
          Sign out
        </Button>
      </div>
    </div>
  );
}
