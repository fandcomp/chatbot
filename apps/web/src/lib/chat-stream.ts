import { apiUrl } from "@/lib/api-client";
import type { StreamSourcesEvent } from "@/lib/chat-schemas";

export type ChatStreamEvent =
  | { type: "token"; text: string }
  | { type: "sources"; data: StreamSourcesEvent }
  | { type: "error"; message: string };

export type ChatStreamResult = {
  conversationId: string | null;
  events: AsyncGenerator<ChatStreamEvent>;
};

/**
 * Hand-rolled SSE client, not the browser's EventSource — EventSource can
 * only issue GET requests with no body, and this endpoint needs POST with a
 * JSON query (ADR-011).
 */
export async function streamChat(
  query: string,
  conversationId: string | undefined,
  signal?: AbortSignal
): Promise<ChatStreamResult> {
  const response = await fetch(apiUrl("/chat/stream"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, conversation_id: conversationId ?? null }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat stream failed with status ${response.status}`);
  }

  return {
    conversationId: response.headers.get("X-Conversation-Id"),
    events: parseEventStream(response.body),
  };
}

async function* parseEventStream(
  body: ReadableStream<Uint8Array>
): AsyncGenerator<ChatStreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separatorIndex = buffer.indexOf("\n\n");
      while (separatorIndex !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        const parsed = parseSseBlock(rawEvent);
        if (parsed) yield parsed;
        separatorIndex = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseBlock(rawEvent: string): ChatStreamEvent | null {
  let eventType = "message";
  const dataLines: string[] = [];

  for (const line of rawEvent.split("\n")) {
    if (line.startsWith("event: ")) {
      eventType = line.slice("event: ".length).trim();
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice("data: ".length));
    }
  }

  if (dataLines.length === 0) return null;
  const data = dataLines.join("\n");

  if (eventType === "sources") {
    return { type: "sources", data: JSON.parse(data) as StreamSourcesEvent };
  }
  if (eventType === "error") {
    return { type: "error", message: data };
  }
  return { type: "token", text: data };
}
