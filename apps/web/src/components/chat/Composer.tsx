"use client";

import { ArrowUpIcon, SquareIcon } from "lucide-react";
import { useState } from "react";
import type { KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";

type Props = {
  isStreaming: boolean;
  onSubmit: (query: string) => void;
  onStop: () => void;
};

export function Composer({ isStreaming, onSubmit, onStop }: Props) {
  const [value, setValue] = useState("");

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    onSubmit(trimmed);
    setValue("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="border-t border-border bg-background px-6 py-4">
      <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-input bg-card px-3 py-2 shadow-sm">
        <textarea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Ask about your regulatory documents…"
          className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-muted-foreground"
        />
        {isStreaming ? (
          <Button type="button" size="icon" variant="secondary" onClick={onStop}>
            <SquareIcon className="size-3.5" />
            <span className="sr-only">Stop generating</span>
          </Button>
        ) : (
          <Button
            type="button"
            size="icon"
            disabled={value.trim().length === 0}
            onClick={handleSubmit}
          >
            <ArrowUpIcon />
            <span className="sr-only">Send</span>
          </Button>
        )}
      </div>
    </div>
  );
}
