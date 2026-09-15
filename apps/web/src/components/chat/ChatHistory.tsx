"use client";

import { Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { ConversationSummary } from "@/lib/chat-schemas";

type Props = {
  conversations: ConversationSummary[];
  activeConversationId: string | undefined;
  onDelete: (id: string) => Promise<void>;
};

function groupLabel(updatedAt: string): string {
  const date = new Date(updatedAt);
  const now = new Date();
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const daysAgo = Math.round(
    (startOfDay(now).getTime() - startOfDay(date).getTime()) / (1000 * 60 * 60 * 24)
  );

  if (daysAgo <= 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  if (daysAgo <= 7) return "Previous 7 days";
  return "Older";
}

export function ChatHistory({ conversations, activeConversationId, onDelete }: Props) {
  // Deleting a conversation permanently removes it and every message in it
  // (spec §90's ConversationService has no soft-delete/undo) — a hover-only
  // trash icon with no confirmation made that one accidental click away.
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConfirmDelete() {
    if (!confirmDeleteId) return;
    setIsDeleting(true);
    setError(null);
    try {
      await onDelete(confirmDeleteId);
      setConfirmDeleteId(null);
    } catch {
      setError("Failed to delete conversation");
    } finally {
      setIsDeleting(false);
    }
  }

  const groups = new Map<string, ConversationSummary[]>();
  for (const conversation of conversations) {
    const label = groupLabel(conversation.updated_at);
    groups.set(label, [...(groups.get(label) ?? []), conversation]);
  }

  if (conversations.length === 0) {
    return <p className="px-2 text-xs text-muted-foreground">No conversations yet.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {error && <p className="px-2 text-xs text-destructive">{error}</p>}
      {Array.from(groups.entries()).map(([label, items]) => (
        <div key={label}>
          <p className="px-2 text-xs font-medium text-muted-foreground">{label}</p>
          <ul className="mt-1 flex flex-col gap-0.5">
            {items.map((conversation) => (
              <li key={conversation.id} className="group/item relative">
                <Link
                  href={`/chat/${conversation.id}`}
                  className={cn(
                    "block truncate rounded-lg px-2 py-1.5 pr-7 text-sm transition-colors",
                    conversation.id === activeConversationId
                      ? "bg-brand-muted text-brand"
                      : "text-foreground hover:bg-muted"
                  )}
                >
                  {conversation.title ?? "New chat"}
                </Link>
                <button
                  type="button"
                  aria-label="Delete conversation"
                  onClick={() => setConfirmDeleteId(conversation.id)}
                  className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded-md p-1 text-muted-foreground opacity-0 hover:bg-muted hover:text-destructive group-hover/item:opacity-100"
                >
                  <Trash2Icon className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <Dialog
        open={confirmDeleteId !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setConfirmDeleteId(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete conversation?</DialogTitle>
            <DialogDescription>
              {(() => {
                const target = conversations.find((c) => c.id === confirmDeleteId);
                const name = target?.title ?? "This conversation";
                return `${name} and all of its messages will be permanently deleted. This cannot be undone.`;
              })()}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmDeleteId(null)}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button variant="destructive" disabled={isDeleting} onClick={() => void handleConfirmDelete()}>
              {isDeleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
