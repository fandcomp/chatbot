import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChatHistory } from "@/components/chat/ChatHistory";
import type { ConversationSummary } from "@/lib/chat-schemas";

// Noon on the real current/offset calendar day, not a relative "hours ago"
// offset — a fixed hour-of-day sidesteps the midnight-boundary flakiness a
// "hours ago" computation hits whenever the suite happens to run close to
// midnight (this test originally failed exactly that way).
function daysAgoAtNoon(days: number): string {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() - days, 12, 0, 0).toISOString();
}

describe("ChatHistory", () => {
  it("shows an empty state when there are no conversations", () => {
    // Arrange & Act
    render(<ChatHistory conversations={[]} activeConversationId={undefined} onDelete={vi.fn()} />);

    // Assert
    expect(screen.getByText(/no conversations yet/i)).toBeInTheDocument();
  });

  it("groups conversations into Today and Previous 7 days", () => {
    // Arrange
    const conversations: ConversationSummary[] = [
      { id: "c1", title: "Today's chat", created_at: daysAgoAtNoon(0), updated_at: daysAgoAtNoon(0) },
      { id: "c2", title: "Older chat", created_at: daysAgoAtNoon(4), updated_at: daysAgoAtNoon(4) },
    ];

    // Act
    render(
      <ChatHistory conversations={conversations} activeConversationId={undefined} onDelete={vi.fn()} />
    );

    // Assert
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("Previous 7 days")).toBeInTheDocument();
    expect(screen.getByText("Today's chat")).toBeInTheDocument();
    expect(screen.getByText("Older chat")).toBeInTheDocument();
  });

  it("falls back to a placeholder title for an untitled conversation", () => {
    // Arrange
    const conversations: ConversationSummary[] = [
      { id: "c1", title: null, created_at: daysAgoAtNoon(0), updated_at: daysAgoAtNoon(0) },
    ];

    // Act
    render(
      <ChatHistory conversations={conversations} activeConversationId={undefined} onDelete={vi.fn()} />
    );

    // Assert
    expect(screen.getByText("New chat")).toBeInTheDocument();
  });

  it("calls onDelete with the conversation id when its delete button is clicked", async () => {
    // Arrange
    const onDelete = vi.fn();
    const user = userEvent.setup();
    const conversations: ConversationSummary[] = [
      { id: "c1", title: "My chat", created_at: daysAgoAtNoon(0), updated_at: daysAgoAtNoon(0) },
    ];
    render(
      <ChatHistory conversations={conversations} activeConversationId={undefined} onDelete={onDelete} />
    );

    // Act
    await user.click(screen.getByRole("button", { name: /delete conversation/i }));

    // Assert
    expect(onDelete).toHaveBeenCalledWith("c1");
  });
});
