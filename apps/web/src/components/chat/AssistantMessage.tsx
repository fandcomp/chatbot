import { renderContentWithCitations } from "@/components/chat/render-citations";
import type { DisplayMessage } from "@/lib/use-chat-session";

type Props = {
  message: DisplayMessage;
  onCiteClick: (sourceId: string) => void;
};

export function AssistantMessage({ message, onCiteClick }: Props) {
  const isEmpty = message.content.length === 0 && message.isStreaming;

  return (
    <div className="flex justify-start">
      <div
        className={
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap " +
          (message.isError
            ? "border border-destructive/30 bg-destructive/10 text-destructive"
            : message.insufficientEvidence
              ? "border border-dashed border-muted-foreground/30 bg-muted/40 text-muted-foreground"
              : "bg-card text-card-foreground")
        }
      >
        {isEmpty ? (
          <span className="inline-flex gap-1">
            <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground" />
            <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:150ms]" />
            <span className="size-1.5 animate-pulse rounded-full bg-muted-foreground [animation-delay:300ms]" />
          </span>
        ) : (
          renderContentWithCitations(message.content, message.citations, onCiteClick)
        )}
        {!isEmpty && message.isStreaming && (
          <span className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse bg-foreground align-text-bottom" />
        )}
      </div>
    </div>
  );
}
