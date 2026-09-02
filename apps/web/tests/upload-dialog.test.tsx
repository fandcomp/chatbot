import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UploadDialog } from "@/components/documents/upload-dialog";

const uploadMock = vi.fn();
const listKnowledgeSpacesMock = vi.fn();

vi.mock("@/lib/documents-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/documents-api")>(
    "@/lib/documents-api"
  );
  return {
    ...actual,
    documentsApi: {
      ...actual.documentsApi,
      listKnowledgeSpaces: () => listKnowledgeSpacesMock(),
      upload: (spaceId: string, file: File) => uploadMock(spaceId, file),
    },
  };
});

function makeFile(name: string, type: string, sizeBytes = 10): File {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

describe("UploadDialog", () => {
  beforeEach(() => {
    uploadMock.mockClear();
    listKnowledgeSpacesMock.mockClear();
    listKnowledgeSpacesMock.mockResolvedValue([
      { id: "space-1", name: "General", created_at: "2026-01-01T00:00:00Z" },
    ]);
  });

  it("opens the dialog and shows the upload form", async () => {
    // Arrange
    const user = userEvent.setup();
    render(<UploadDialog onUploaded={vi.fn()} />);

    // Act
    await user.click(screen.getByRole("button", { name: /upload document/i }));

    // Assert
    expect(await screen.findByText(/drop document here/i)).toBeInTheDocument();
  });

  it("rejects a disallowed file extension without calling the API", async () => {
    // Arrange
    const user = userEvent.setup();
    render(<UploadDialog onUploaded={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    await screen.findByText(/drop document here/i);

    const fileInput = document.getElementById("file-input") as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [makeFile("notes.txt", "text/plain")] } });

    // Act
    await user.click(screen.getByRole("button", { name: /^upload$/i }));

    // Assert
    expect(await screen.findByText(/only pdf or docx/i)).toBeInTheDocument();
    expect(uploadMock).not.toHaveBeenCalled();
  });

  it("uploads a valid file and reports success", async () => {
    // Arrange
    uploadMock.mockResolvedValueOnce({
      document_id: "doc-1",
      document_version_id: "ver-1",
      processing_job_id: "job-1",
      status: "UPLOADED",
    });
    const onUploaded = vi.fn();
    const user = userEvent.setup();
    render(<UploadDialog onUploaded={onUploaded} />);
    await user.click(screen.getByRole("button", { name: /upload document/i }));
    await screen.findByText(/drop document here/i);

    const fileInput = document.getElementById("file-input") as HTMLInputElement;
    fireEvent.change(fileInput, {
      target: { files: [makeFile("report.pdf", "application/pdf")] },
    });

    // Act
    await user.click(screen.getByRole("button", { name: /^upload$/i }));

    // Assert
    expect(uploadMock).toHaveBeenCalledWith("space-1", expect.any(File));
    await vi.waitFor(() => expect(onUploaded).toHaveBeenCalled());
  });
});
