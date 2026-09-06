import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TestKnowledgePanel } from "@/components/documents/test-knowledge-panel";

const testKnowledgeMock = vi.fn();

vi.mock("@/lib/documents-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/documents-api")>(
    "@/lib/documents-api"
  );
  return {
    ...actual,
    documentsApi: {
      ...actual.documentsApi,
      testKnowledge: (documentId: string, query: string) => testKnowledgeMock(documentId, query),
    },
  };
});

describe("TestKnowledgePanel", () => {
  it("submits the query against the given document and renders the result", async () => {
    // Arrange
    testKnowledgeMock.mockResolvedValueOnce({
      question: "Apa isi Pasal 5?",
      detected_intent: "FACTUAL_LOOKUP",
      retrieval_mode: "EXACT_STRUCTURAL",
      retrieved_sources: [
        {
          chunk_id: "chunk-1",
          structural_path_text: "Pasal 5",
          original_text: "Ketentuan sumber asli mengenai pendidikan dasar.",
          score: null,
        },
      ],
      answer: "Berdasarkan Pasal 5, setiap warga negara berhak atas pendidikan. [S1]",
      insufficient_evidence: false,
      reason_if_insufficient: null,
      citations: {
        S1: {
          source_id: "S1",
          document_id: "doc-1",
          document_title: "Peraturan X",
          structural_path_text: "Pasal 5",
          page_start: 1,
          page_end: 1,
          original_text_excerpt: "Setiap warga negara berhak atas pendidikan.",
        },
      },
    });
    const user = userEvent.setup();
    render(<TestKnowledgePanel documentId="doc-1" />);

    // Act
    await user.type(screen.getByLabelText(/question/i), "Apa isi Pasal 5?");
    await user.click(screen.getByRole("button", { name: /^test$/i }));

    // Assert
    expect(testKnowledgeMock).toHaveBeenCalledWith("doc-1", "Apa isi Pasal 5?");
    expect(await screen.findByText("FACTUAL_LOOKUP")).toBeInTheDocument();
    expect(
      screen.getByText("Berdasarkan Pasal 5, setiap warga negara berhak atas pendidikan. [S1]")
    ).toBeInTheDocument();
    expect(screen.getByText("Ketentuan sumber asli mengenai pendidikan dasar.")).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    // Arrange
    testKnowledgeMock.mockRejectedValueOnce(new Error("boom"));
    const user = userEvent.setup();
    render(<TestKnowledgePanel documentId="doc-1" />);

    // Act
    await user.type(screen.getByLabelText(/question/i), "Apa isi Pasal 5?");
    await user.click(screen.getByRole("button", { name: /^test$/i }));

    // Assert
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });

  it("disables the Test button until a question is entered", () => {
    // Arrange & Act
    render(<TestKnowledgePanel documentId="doc-1" />);

    // Assert
    expect(screen.getByRole("button", { name: /^test$/i })).toBeDisabled();
  });
});
