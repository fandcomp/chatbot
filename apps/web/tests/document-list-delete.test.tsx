import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentList } from "@/components/documents/document-list";
import { AuthProvider } from "@/lib/auth-context";
import type { DocumentItem } from "@/lib/documents-api";

const listDocumentsMock = vi.fn();
const deleteDocumentMock = vi.fn();

vi.mock("@/lib/documents-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/documents-api")>(
    "@/lib/documents-api"
  );
  return {
    ...actual,
    documentsApi: {
      ...actual.documentsApi,
      listDocuments: () => listDocumentsMock(),
      deleteDocument: (id: string) => deleteDocumentMock(id),
    },
  };
});

const SAMPLE_DOCUMENT: DocumentItem = {
  id: "doc-1",
  title: "Sample Regulation",
  knowledge_space_id: "ks-1",
  visibility: "PUBLIC",
  latest_version_id: "ver-1",
  latest_version_status: "ACTIVE",
  latest_processing_job_id: null,
  created_at: "2026-01-01T00:00:00Z",
};

function renderList() {
  return render(
    <AuthProvider>
      <DocumentList refreshToken={0} />
    </AuthProvider>
  );
}

// Regression coverage for the gap audit 2026-09-15 frontend pass: Delete is a
// permanent, cascading action (versions, chunks, Qdrant points, storage —
// see apps/api/app/documents/router.py's delete_document) with no undo path,
// but the button previously called the API directly with zero confirmation.
describe("DocumentList delete confirmation", () => {
  beforeEach(() => {
    listDocumentsMock.mockReset();
    deleteDocumentMock.mockReset();
    listDocumentsMock.mockResolvedValue([SAMPLE_DOCUMENT]);
  });

  it("does not call the delete API until the user confirms", async () => {
    // Arrange
    const user = userEvent.setup();
    renderList();
    await screen.findByText("Sample Regulation");

    // Act
    await user.click(screen.getByRole("button", { name: /^delete$/i }));

    // Assert
    expect(deleteDocumentMock).not.toHaveBeenCalled();
    expect(await screen.findByText(/delete document\?/i)).toBeInTheDocument();
  });

  it("cancelling leaves the document untouched", async () => {
    // Arrange
    const user = userEvent.setup();
    renderList();
    await screen.findByText("Sample Regulation");
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    await screen.findByText(/delete document\?/i);

    // Act
    await user.click(screen.getByRole("button", { name: /cancel/i }));

    // Assert
    expect(deleteDocumentMock).not.toHaveBeenCalled();
    expect(screen.queryByText(/delete document\?/i)).not.toBeInTheDocument();
    expect(screen.getByText("Sample Regulation")).toBeInTheDocument();
  });

  it("confirming deletes the document and removes it from the list", async () => {
    // Arrange
    deleteDocumentMock.mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    renderList();
    await screen.findByText("Sample Regulation");
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");

    // Act
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    // Assert
    expect(deleteDocumentMock).toHaveBeenCalledWith("doc-1");
    await waitFor(() =>
      expect(screen.queryByText("Sample Regulation")).not.toBeInTheDocument()
    );
  });

  it("surfaces an error and keeps the document if deletion fails", async () => {
    // Arrange
    deleteDocumentMock.mockRejectedValueOnce(new Error("boom"));
    const user = userEvent.setup();
    renderList();
    await screen.findByText("Sample Regulation");
    await user.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");

    // Act
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    // Assert
    await waitFor(() => expect(deleteDocumentMock).toHaveBeenCalled());
    expect(screen.getByText("Sample Regulation")).toBeInTheDocument();
  });
});
