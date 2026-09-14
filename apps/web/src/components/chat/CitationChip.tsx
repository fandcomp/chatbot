"use client";

import { cn } from "@/lib/utils";

type Props = {
  sourceId: string;
  isKnown: boolean;
  // spec §21 — this source's document has been amended/repealed/replaced by
  // another one (superseding_relations non-empty). Surfaced here as a small
  // marker so the warning is visible before a user even opens the source
  // drawer, not only inside it.
  hasWarning?: boolean;
  onClick: (sourceId: string) => void;
};

export function CitationChip({ sourceId, isKnown, hasWarning, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={() => onClick(sourceId)}
      disabled={!isKnown}
      className={cn(
        "relative mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 align-text-top text-[0.7rem] font-medium transition-colors",
        isKnown
          ? "bg-brand-muted text-brand hover:bg-brand hover:text-brand-foreground"
          : "bg-muted text-muted-foreground"
      )}
    >
      {sourceId}
      {hasWarning && (
        <span
          aria-label="This source may have been amended, repealed, or replaced"
          className="absolute -top-0.5 -right-0.5 size-2 rounded-full bg-amber-500 ring-1 ring-card"
        />
      )}
    </button>
  );
}
