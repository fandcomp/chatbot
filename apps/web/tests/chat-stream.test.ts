import { afterEach, describe, expect, it, vi } from "vitest";

import { streamChat } from "@/lib/chat-stream";

vi.mock("@/lib/api-client", () => ({
  apiUrl: (path: string) => `https://api.test${path}`,
}));

function sseResponse(chunks: string[], init: ResponseInit = {}): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "X-Conversation-Id": "conv-1" },
    ...init,
  });
}

async function collectEvents(chunks: string[]) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(chunks)));
  const { events } = await streamChat("Apa isi Pasal 5?", undefined);
  const collected = [];
  for await (const event of events) collected.push(event);
  return collected;
}

describe("streamChat", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the conversation id from the response header", async () => {
    // Arrange
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(["event: message\ndata: hi\n\n"])));

    // Act
    const { conversationId } = await streamChat("query", undefined);

    // Assert
    expect(conversationId).toBe("conv-1");
  });

  it("throws when the response is not ok", async () => {
    // Arrange
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 500 }))
    );

    // Act & Assert
    await expect(streamChat("query", undefined)).rejects.toThrow(/status 500/);
  });

  it("parses a plain token event with no explicit event: line", async () => {
    // Act
    const events = await collectEvents(["data: Halo\n\n"]);

    // Assert
    expect(events).toEqual([{ type: "token", text: "Halo" }]);
  });

  it("parses a sources event as JSON", async () => {
    // Arrange
    const sources = { insufficient_evidence: false, claims: [], citations: {} };

    // Act
    const events = await collectEvents([
      `event: sources\ndata: ${JSON.stringify(sources)}\n\n`,
    ]);

    // Assert
    expect(events).toEqual([{ type: "sources", data: sources }]);
  });

  it("parses an error event", async () => {
    // Act
    const events = await collectEvents(["event: error\ndata: LLM provider unavailable\n\n"]);

    // Assert
    expect(events).toEqual([{ type: "error", message: "LLM provider unavailable" }]);
  });

  it("reassembles an SSE event split across multiple stream chunks", async () => {
    // A real HTTP stream can split a single SSE block anywhere, including
    // mid-line — the parser's buffering must not lose or duplicate data.
    const events = await collectEvents(["event: tok", "en\ndata: Ha", "lo\n\n"]);

    expect(events).toEqual([{ type: "token", text: "Halo" }]);
  });

  it("parses multiple consecutive events delivered in one chunk", async () => {
    // Act
    const events = await collectEvents([
      "data: Hal\n\ndata: o dunia\n\nevent: error\ndata: boom\n\n",
    ]);

    // Assert
    expect(events).toEqual([
      { type: "token", text: "Hal" },
      { type: "token", text: "o dunia" },
      { type: "error", message: "boom" },
    ]);
  });

  it("ignores a trailing partial event with no terminating blank line", async () => {
    // A stream that ends mid-event (connection dropped) must not yield a
    // half-formed event — only the complete, terminated block is emitted.
    const events = await collectEvents(["data: complete\n\ndata: incomplete-no-terminator"]);

    expect(events).toEqual([{ type: "token", text: "complete" }]);
  });
});
