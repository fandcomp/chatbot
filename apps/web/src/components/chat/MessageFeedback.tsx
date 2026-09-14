"use client";

import { ThumbsDownIcon, ThumbsUpIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api-client";
import { chatApi, type FeedbackRating } from "@/lib/chat-api";
import { cn } from "@/lib/utils";

type Props = {
  messageId: string;
};

export function MessageFeedback({ messageId }: Props) {
  const [submitted, setSubmitted] = useState<FeedbackRating | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRate(rating: FeedbackRating) {
    if (isSubmitting || submitted) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await chatApi.submitFeedback(messageId, rating);
      setSubmitted(rating);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Feedback failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex items-center gap-0.5 pl-1">
      <Button
        variant="ghost"
        size="icon-xs"
        disabled={isSubmitting || submitted !== null}
        aria-label="Good response"
        aria-pressed={submitted === "THUMBS_UP"}
        onClick={() => void handleRate("THUMBS_UP")}
        className={cn(submitted === "THUMBS_UP" && "text-brand")}
      >
        <ThumbsUpIcon />
      </Button>
      <Button
        variant="ghost"
        size="icon-xs"
        disabled={isSubmitting || submitted !== null}
        aria-label="Bad response"
        aria-pressed={submitted === "THUMBS_DOWN"}
        onClick={() => void handleRate("THUMBS_DOWN")}
        className={cn(submitted === "THUMBS_DOWN" && "text-destructive")}
      >
        <ThumbsDownIcon />
      </Button>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
}
