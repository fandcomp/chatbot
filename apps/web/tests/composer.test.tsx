import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Composer } from "@/components/chat/Composer";

describe("Composer", () => {
  it("submits the trimmed query and clears the input", async () => {
    // Arrange
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Composer isStreaming={false} onSubmit={onSubmit} onStop={vi.fn()} />);
    const textarea = screen.getByPlaceholderText(/ask about your regulatory documents/i);

    // Act
    await user.type(textarea, "  Apa isi Pasal 5?  ");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Assert
    expect(onSubmit).toHaveBeenCalledWith("Apa isi Pasal 5?");
    expect(textarea).toHaveValue("");
  });

  it("submits on Enter without Shift", async () => {
    // Arrange
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Composer isStreaming={false} onSubmit={onSubmit} onStop={vi.fn()} />);

    // Act
    await user.type(
      screen.getByPlaceholderText(/ask about your regulatory documents/i),
      "Apa isi Pasal 5?{Enter}"
    );

    // Assert
    expect(onSubmit).toHaveBeenCalledWith("Apa isi Pasal 5?");
  });

  it("does not submit an empty or whitespace-only query", async () => {
    // Arrange
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Composer isStreaming={false} onSubmit={onSubmit} onStop={vi.fn()} />);

    // Act
    await user.type(screen.getByPlaceholderText(/ask about your regulatory documents/i), "   {Enter}");

    // Assert
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("shows a stop button while streaming instead of send", async () => {
    // Arrange
    const onStop = vi.fn();
    const user = userEvent.setup();
    render(<Composer isStreaming={true} onSubmit={vi.fn()} onStop={onStop} />);

    // Act
    await user.click(screen.getByRole("button", { name: /stop generating/i }));

    // Assert
    expect(onStop).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /^send$/i })).not.toBeInTheDocument();
  });
});
