import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderContentWithCitations } from "@/components/chat/render-citations";
import type { Citation } from "@/lib/chat-schemas";

function makeCitation(sourceId: string): Citation {
  return {
    source_id: sourceId,
    document_id: "doc-1",
    document_title: "Peraturan X",
    structural_path_text: "Pasal 5",
    page_start: 1,
    page_end: 1,
    original_text_excerpt: "Setiap warga negara berhak atas pendidikan.",
  };
}

describe("renderContentWithCitations", () => {
  it("renders plain text unchanged when there are no markers", () => {
    // Arrange & Act
    render(<div>{renderContentWithCitations("No citations here.", undefined, vi.fn())}</div>);

    // Assert
    expect(screen.getByText("No citations here.")).toBeInTheDocument();
  });

  it("splits text and renders a clickable chip for a known source", async () => {
    // Arrange
    const onCiteClick = vi.fn();
    const user = userEvent.setup();
    render(
      <div>
        {renderContentWithCitations(
          "Setiap warga negara berhak atas pendidikan. [S1]",
          { S1: makeCitation("S1") },
          onCiteClick
        )}
      </div>
    );

    // Act
    await user.click(screen.getByRole("button", { name: "S1" }));

    // Assert
    expect(onCiteClick).toHaveBeenCalledWith("S1");
  });

  it("renders multiple labels from one marker as separate chips", () => {
    // Arrange & Act
    render(
      <div>
        {renderContentWithCitations(
          "Ketentuan ini konsisten. [S1, S2]",
          { S1: makeCitation("S1"), S2: makeCitation("S2") },
          vi.fn()
        )}
      </div>
    );

    // Assert
    expect(screen.getByRole("button", { name: "S1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "S2" })).toBeInTheDocument();
  });

  it("disables a chip whose source id was never provided", () => {
    // Arrange & Act
    render(<div>{renderContentWithCitations("Klaim ini. [S9]", {}, vi.fn())}</div>);

    // Assert
    expect(screen.getByRole("button", { name: "S9" })).toBeDisabled();
  });
});
