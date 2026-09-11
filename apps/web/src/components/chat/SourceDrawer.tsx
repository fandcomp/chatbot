"use client";

import { XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/chat-schemas";

type Props = {
  citation: Citation | null;
  onClose: () => void;
};

export function SourceDrawer({ citation, onClose }: Props) {
  if (!citation) return null;

  return (
    <>
      <button
        type="button"
        aria-label="Close source panel"
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/10 md:hidden"
      />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card md:w-[380px]">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">Source</h2>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
            <XIcon />
            <span className="sr-only">Close</span>
          </Button>
        </div>
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-4">
          <div>
            <p className="text-sm font-medium">{citation.document_title}</p>
            {citation.structural_path_text && (
              <p className="mt-1 text-sm text-muted-foreground">
                {citation.structural_path_text}
              </p>
            )}
            {citation.page_start !== null && (
              <p className="mt-1 text-xs text-muted-foreground">
                Page {citation.page_start}
                {citation.page_end !== citation.page_start ? `–${citation.page_end}` : ""}
              </p>
            )}
          </div>
          <div className="rounded-lg border border-border bg-muted/30 p-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Original text
            </p>
            <p className="mt-2 text-sm whitespace-pre-wrap">{citation.original_text_excerpt}</p>
          </div>
        </div>
      </aside>
    </>
  );
}
