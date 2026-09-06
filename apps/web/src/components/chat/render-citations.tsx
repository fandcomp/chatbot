import type { ReactNode } from "react";

import { CitationChip } from "@/components/chat/CitationChip";
import type { Citation } from "@/lib/chat-schemas";

const MARKER_RE = /\[\s*((?:S\d+\s*,?\s*)+)\]/g;
const LABEL_RE = /S\d+/g;

/**
 * Turns "...text [S1, S2]" into text interspersed with clickable
 * CitationChip nodes — the display-side counterpart of the backend's
 * app/chat/inline_citation_parser.py.
 */
export function renderContentWithCitations(
  content: string,
  citations: Record<string, Citation> | undefined,
  onCiteClick: (sourceId: string) => void
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  MARKER_RE.lastIndex = 0;
  while ((match = MARKER_RE.exec(content)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(content.slice(lastIndex, match.index));
    }
    const labels = match[1].match(LABEL_RE) ?? [];
    for (const label of labels) {
      nodes.push(
        <CitationChip
          key={`${label}-${key++}`}
          sourceId={label}
          isKnown={Boolean(citations?.[label])}
          onClick={onCiteClick}
        />
      );
    }
    lastIndex = MARKER_RE.lastIndex;
  }

  if (lastIndex < content.length) {
    nodes.push(content.slice(lastIndex));
  }

  return nodes;
}
