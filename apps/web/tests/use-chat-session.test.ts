import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useChatSession } from "@/lib/use-chat-session";

const streamChatMock = vi.fn();

vi.mock("@/lib/chat-stream", () => ({
  streamChat: (...args: unknown[]) => streamChatMock(...args),
}));

async function* eventsFrom(events: unknown[]) {
  for (const event of events) yield event;
}

describe("useChatSession", () => {
  beforeEach(() => {
    streamChatMock.mockReset();
  });

  it("streams tokens into the assistant message as they arrive", async () => {
    // Arrange
    streamChatMock.mockResolvedValue({
      conversationId: "conv-1",
      events: eventsFrom([
        { type: "token", text: "Hal" },
        { type: "token", text: "o dunia" },
        {
          type: "sources",
          data: { insufficient_evidence: false, claims: [], citations: {} },
        },
      ]),
    });
    const onConversationCreated = vi.fn();
    const { result } = renderHook(() =>
      useChatSession(undefined, { onConversationCreated })
    );

    // Act
    await act(async () => {
      await result.current.sendMessage("Apa isi Pasal 5?");
    });

    // Assert
    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]).toMatchObject({ role: "USER", content: "Apa isi Pasal 5?" });
    expect(result.current.messages[1]).toMatchObject({
      role: "ASSISTANT",
      content: "Halo dunia",
      isStreaming: false,
      insufficientEvidence: false,
    });
    expect(result.current.isStreaming).toBe(false);
    expect(onConversationCreated).toHaveBeenCalledWith("conv-1");
  });

  it("does not report a new conversation id when continuing an existing conversation", async () => {
    // Arrange
    streamChatMock.mockResolvedValue({
      conversationId: "conv-1",
      events: eventsFrom([{ type: "token", text: "Halo" }]),
    });
    const onConversationCreated = vi.fn();
    const { result } = renderHook(() =>
      useChatSession("conv-1", { onConversationCreated })
    );

    // Act
    await act(async () => {
      await result.current.sendMessage("Lanjutkan");
    });

    // Assert
    expect(onConversationCreated).not.toHaveBeenCalled();
  });

  it("appends a generic error message and marks the message as errored on a mid-stream error event", async () => {
    // Arrange
    streamChatMock.mockResolvedValue({
      conversationId: null,
      events: eventsFrom([
        { type: "token", text: "Sebagian jawaban" },
        { type: "error", message: "LLM provider unavailable" },
      ]),
    });
    const { result } = renderHook(() => useChatSession(undefined));

    // Act
    await act(async () => {
      await result.current.sendMessage("query");
    });

    // Assert — partial output must be preserved, not discarded (see the
    // comment in use-chat-session.ts on why this appends rather than replaces).
    expect(result.current.messages[1].content).toBe(
      "Sebagian jawaban\n\nSomething went wrong while generating a response. Please try again."
    );
    expect(result.current.messages[1].isError).toBe(true);
    expect(result.current.messages[1].isStreaming).toBe(false);
    expect(result.current.error).toBe("LLM provider unavailable");
  });

  it("marks the assistant message as errored when streamChat itself rejects", async () => {
    // Arrange
    streamChatMock.mockRejectedValue(new Error("Chat stream failed with status 502"));
    const { result } = renderHook(() => useChatSession(undefined));

    // Act
    await act(async () => {
      await result.current.sendMessage("query");
    });

    // Assert
    expect(result.current.messages[1]).toMatchObject({
      content: "Something went wrong while generating a response. Please try again.",
      isError: true,
      isStreaming: false,
    });
    expect(result.current.error).toBe("Chat stream failed with status 502");
    expect(result.current.isStreaming).toBe(false);
  });

  it("does not surface an error when the stream is intentionally aborted", async () => {
    // Arrange — stopStreaming aborts mid-generation; the hook must treat
    // AbortError as a silent, expected outcome, not a failure to surface.
    streamChatMock.mockRejectedValue(new DOMException("Aborted", "AbortError"));
    const { result } = renderHook(() => useChatSession(undefined));

    // Act
    await act(async () => {
      await result.current.sendMessage("query");
    });

    // Assert
    expect(result.current.error).toBeNull();
    expect(result.current.isStreaming).toBe(false);
    // The assistant placeholder is left as-is (still marked streaming) —
    // the abort path returns early without finalizing it, matching the
    // real UI's expectation that stopStreaming() is a deliberate user action.
    expect(result.current.messages[1].isError).toBeFalsy();
  });

  it("stopStreaming aborts the in-flight request", async () => {
    // Arrange
    let capturedSignal: AbortSignal | undefined;
    streamChatMock.mockImplementation(async (_query: string, _conversationId: unknown, signal: AbortSignal) => {
      capturedSignal = signal;
      return { conversationId: null, events: eventsFrom([]) };
    });
    const { result } = renderHook(() => useChatSession(undefined));

    // Act
    await act(async () => {
      const promise = result.current.sendMessage("query");
      result.current.stopStreaming();
      await promise;
    });

    // Assert
    await waitFor(() => expect(capturedSignal?.aborted).toBe(true));
  });
});
