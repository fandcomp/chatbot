"use client";

import { cn } from "@/lib/utils";

type Props = {
  sourceId: string;
  isKnown: boolean;
  onClick: (sourceId: string) => void;
};

export function CitationChip({ sourceId, isKnown, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={() => onClick(sourceId)}
      disabled={!isKnown}
      className={cn(
        "mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 align-text-top text-[0.7rem] font-medium transition-colors",
        isKnown
          ? "bg-brand-muted text-brand hover:bg-brand hover:text-brand-foreground"
          : "bg-muted text-muted-foreground"
      )}
    >
      {sourceId}
    </button>
  );
}
